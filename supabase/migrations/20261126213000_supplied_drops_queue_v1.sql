-- Supplied-document drops, queued (approved by Larry 26 Nov 2026: encrypted drops
-- may live on the supplied-drops branch of the public worker repo).
-- Each drop file is base64(IV[16] || AES-256-CBC ciphertext) of a JSON document:
--   {doc, title, pages, review_state, extraction, verification, sections, rows}
-- The key is held only in rv_private.supplied_drop_keys_v1 (never committed).
-- fetch_supplied_drops_v1() asks pg_net to download queued drops;
-- ingest_supplied_drops_v1() decrypts each 200 response, registers the document,
-- loads its rows and publishes it when its automated gates passed (review_state
-- 'reviewed'); documents that failed a gate are registered 'unreviewed' and held.

create table if not exists rv_private.supplied_drop_keys_v1 (
  id         text primary key,
  key_hex    text not null check (key_hex ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now()
);
revoke all on rv_private.supplied_drop_keys_v1 from public, anon, authenticated;

create table if not exists rv_private.supplied_drops_v1 (
  name       text primary key check (name ~ '^[0-9a-f]{16}$'),
  url        text not null check (url like 'https://raw.githubusercontent.com/hayesel-hash/camperpartfinder-worker/supplied-drops/%'),
  key_id     text not null references rv_private.supplied_drop_keys_v1(id),
  source_id  text not null references rv_private.sources(id),
  publisher  text not null references rv_private.manufacturers(name),
  supplied_by  text not null,
  obtained_via text not null,
  status     text not null default 'queued' check (status in ('queued','fetching','done','failed')),
  request_id bigint,
  result     jsonb,
  updated_at timestamptz not null default now()
);
revoke all on rv_private.supplied_drops_v1 from public, anon, authenticated;

create or replace function rv_private.fetch_supplied_drops_v1()
returns integer language plpgsql set search_path to 'pg_catalog' as $fn$
declare d record; n integer := 0;
begin
  for d in select * from rv_private.supplied_drops_v1 where status = 'queued' order by name loop
    update rv_private.supplied_drops_v1
       set request_id = net.http_get(d.url, timeout_milliseconds := 60000), status = 'fetching', updated_at = now()
     where name = d.name;
    n := n + 1;
  end loop;
  return n;
end;
$fn$;
revoke all on function rv_private.fetch_supplied_drops_v1() from public, anon, authenticated;

create or replace function rv_private.ingest_supplied_drops_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare d record; resp record; raw bytea; plain jsonb; k text; loaded integer; pub jsonb;
        done integer := 0; failed integer := 0; waiting integer := 0;
begin
  for d in select * from rv_private.supplied_drops_v1 where status = 'fetching' order by name loop
    select r.status_code, r.content, r.timed_out, r.error_msg into resp from net._http_response r where r.id = d.request_id;
    if not found then waiting := waiting + 1; continue; end if;
    if resp.status_code is distinct from 200 then
      update rv_private.supplied_drops_v1 set status = 'failed', updated_at = now(),
             result = jsonb_build_object('http', resp.status_code, 'timed_out', resp.timed_out, 'error', resp.error_msg)
       where name = d.name;
      failed := failed + 1; continue;
    end if;
    begin
      select key_hex into k from rv_private.supplied_drop_keys_v1 where id = d.key_id;
      raw := decode(resp.content, 'base64');
      plain := convert_from(extensions.decrypt_iv(substring(raw from 17), decode(k, 'hex'), substring(raw from 1 for 16),
                                                  'aes-cbc/pad:pkcs'), 'UTF8')::jsonb;
      if left(plain->>'doc', 16) <> d.name then raise exception 'drop name does not match document hash'; end if;
      insert into rv_private.supplied_documents_v1(sha256, source_id, publisher, title, pages, supplied_by, obtained_via,
                                                    extraction, verification, review_state)
      values (plain->>'doc', d.source_id, d.publisher, plain->>'title', (plain->>'pages')::int, d.supplied_by, d.obtained_via,
              plain->>'extraction', plain->>'verification', plain->>'review_state')
      on conflict (sha256) do nothing;
      loaded := rv_private.load_supplied_rows_v1(plain->>'doc', plain->'sections', plain->>'rows');
      pub := case when plain->>'review_state' = 'reviewed'
                  then rv_private.publish_supplied_document_v1(plain->>'doc') else '{"held":"gates failed"}'::jsonb end;
      update rv_private.supplied_drops_v1 set status = 'done', updated_at = now(),
             result = jsonb_build_object('title', plain->>'title', 'rows_loaded', loaded) || pub
       where name = d.name;
      done := done + 1;
    exception when others then
      update rv_private.supplied_drops_v1 set status = 'failed', updated_at = now(),
             result = jsonb_build_object('error', sqlerrm) where name = d.name;
      failed := failed + 1;
    end;
  end loop;
  return jsonb_build_object('done', done, 'failed', failed, 'waiting', waiting);
end;
$fn$;
revoke all on function rv_private.ingest_supplied_drops_v1() from public, anon, authenticated;
