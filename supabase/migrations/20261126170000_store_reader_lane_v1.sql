-- Store reader lane v1: read makers' (and later distributors') own online parts
-- stores, which is where most RV component part numbers are published.
-- First store: Lippert (www.lippert.com) — supplies most Thor, Forest River,
-- Keystone, Jayco and Grand Design rigs; robots.txt allows product pages and
-- publishes a product sitemap. Approved under Larry's blanket approval, 26 Nov 2026.
--
-- Flow: workflow store-reader.yml -> rv-store-gateway (GitHub OIDC; stage-only)
--   frontier: sitemap product URLs -> store_frontier_v1
--   claim/stage: page facts (SKU, name, brand, compatibility wording) -> store_products_v1
-- Publication: publish_store_identities_v1, only for a REVIEWED store, only the
-- maker's own brands (brand_allowlist), only rows with SKU and name. Identity
-- evidence = the product page (URL + SHA-256 + quoted SKU line).
-- Compatibility wording is staged for later review; nothing here publishes a
-- relationship.
--
-- Rollback: unschedule rv-store-identities-v1; set store_sources_v1.enabled=false;
-- parts published by this lane carry audit action automated_store_identity_publish
-- and identity_evidence reviewer 'store-reader-v1' (withdraw with state='withdrawn').

create table if not exists rv_private.store_sources_v1 (
  id                  text primary key,
  publisher           text not null references rv_private.manufacturers(name),
  authority           text not null check (authority in ('manufacturer','distributor')),
  host                text not null,
  sitemap_url         text not null,
  product_url_pattern text not null,
  brand_allowlist     text[] not null default '{}',
  source_id           text not null references rv_private.sources(id),
  enabled             boolean not null default true,
  review_state        text not null default 'unreviewed' check (review_state in ('unreviewed','reviewed','rejected')),
  reviewed_by text, reviewed_at timestamptz, review_note text,
  frontier_loaded_at  timestamptz,
  created_at          timestamptz not null default now()
);

create table if not exists rv_private.store_frontier_v1 (
  store_id    text not null references rv_private.store_sources_v1(id),
  url         text not null,
  state       text not null default 'pending' check (state in ('pending','leased','done','failed')),
  attempts    integer not null default 0,
  lease       uuid,
  lease_until timestamptz,
  last_error  text,
  first_seen  timestamptz not null default now(),
  fetched_at  timestamptz,
  primary key (store_id, url)
);
create index if not exists store_frontier_v1_todo on rv_private.store_frontier_v1 (store_id, state) where state in ('pending','failed');

create table if not exists rv_private.store_products_v1 (
  store_id    text not null references rv_private.store_sources_v1(id),
  url         text not null,
  page_sha256 text not null check (page_sha256 ~ '^[0-9a-f]{64}$'),
  fetched_at  timestamptz not null,
  sku         text,
  name        text,
  brand       text,
  compat      jsonb not null default '[]' check (jsonb_typeof(compat) = 'array'),
  status      text not null default 'staged' check (status in ('staged','held','published')),
  hold_reason text,
  part_id     uuid references rv_private.parts(id),
  staged_at   timestamptz not null default now(),
  primary key (store_id, url, page_sha256)
);
create index if not exists store_products_v1_open on rv_private.store_products_v1 (store_id, status) where status = 'staged';

-- Lippert: manufacturer, source row (not a PDF, so the catalogue router ignores it).
insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('lippert-store', 'Lippert', 'https://www.lippert.com/', 'PUBLIC_FACTS',
        jsonb_build_object('kind','manufacturer','scope','Lippert own online store: product pages (SKU, name, brand); identities only',
          'robotsReview','robots.txt allows product pages; Content-Signal search=yes, ai-train=no, use=reference (checked 26 Nov 2026); no AI training use',
          'approvedBy','Larry, blanket approval 26 Nov 2026','bulkEnabled',false))
on conflict (id) do nothing;

insert into rv_private.store_sources_v1(id, publisher, authority, host, sitemap_url, product_url_pattern, brand_allowlist, source_id)
values ('lippert-store', 'Lippert', 'manufacturer', 'www.lippert.com',
        'https://www.lippert.com/media/sitemap/sitemap.xml',
        '^https://www\.lippert\.com/[a-z0-9-]+-(v?[0-9]{5,10})-\1$',
        array['Lippert','LCI','Lippert Components','Solera','Furrion','Kwikee','Schwintek','Power Gear','Ground Control','OneControl','Kinro'],
        'lippert-store')
on conflict (id) do nothing;

-- Gateway RPCs (service role only) -------------------------------------------
create or replace function public.rv_store_config()
returns jsonb language sql security definer set search_path to 'pg_catalog' as $fn$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', id, 'host', host, 'sitemap_url', sitemap_url, 'product_url_pattern', product_url_pattern,
    'needs_frontier', frontier_loaded_at is null or frontier_loaded_at < now() - interval '7 days',
    'todo', (select count(*) from rv_private.store_frontier_v1 f where f.store_id = s.id and f.state in ('pending','failed')))), '[]'::jsonb)
  from rv_private.store_sources_v1 s where enabled;
$fn$;

create or replace function public.rv_store_frontier(store text, urls jsonb, final boolean)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare s record; n integer;
begin
  select * into s from rv_private.store_sources_v1 where id = store and enabled;
  if not found or jsonb_typeof(urls) <> 'array' or jsonb_array_length(urls) > 20000 then
    return jsonb_build_object('error','invalid');
  end if;
  insert into rv_private.store_frontier_v1(store_id, url)
  select s.id, u from jsonb_array_elements_text(urls) u
  where u ~ s.product_url_pattern and length(u) < 600
  on conflict do nothing;
  get diagnostics n = row_count;
  if final then update rv_private.store_sources_v1 set frontier_loaded_at = now() where id = s.id; end if;
  return jsonb_build_object('added', n);
end;
$fn$;

create or replace function public.rv_store_claim(store text, n integer)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare tok uuid := gen_random_uuid(); urls jsonb;
begin
  with c as (
    select url from rv_private.store_frontier_v1
     where store_id = store
       and (state = 'pending'
            or (state = 'failed' and attempts < 3 and coalesce(fetched_at, first_seen) < now() - interval '1 hour')
            or (state = 'leased' and lease_until < now()))
     order by state, first_seen, url
     limit least(greatest(n,1), 200)
     for update skip locked)
  update rv_private.store_frontier_v1 f
     set state = 'leased', lease = tok, lease_until = now() + interval '30 minutes', attempts = f.attempts + 1
    from c where f.store_id = store and f.url = c.url;
  select coalesce(jsonb_agg(url), '[]'::jsonb) into urls from rv_private.store_frontier_v1 where store_id = store and lease = tok;
  return jsonb_build_object('lease', tok, 'urls', urls);
end;
$fn$;

create or replace function public.rv_store_stage(store text, tok uuid, rows jsonb)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare n integer := 0; d integer := 0;
begin
  if jsonb_typeof(rows) <> 'array' or jsonb_array_length(rows) > 200 then return jsonb_build_object('error','invalid'); end if;
  insert into rv_private.store_products_v1(store_id, url, page_sha256, fetched_at, sku, name, brand, compat)
  select store, x.url, x.page_sha256, x.fetched_at, left(x.sku,60), left(x.name,240), left(x.brand,80),
         coalesce((select jsonb_agg(left(e,300)) from jsonb_array_elements_text(coalesce(x.compat,'[]')) with ordinality t(e,i) where i <= 8), '[]')
  from jsonb_to_recordset(rows) as x(url text, page_sha256 text, fetched_at timestamptz, sku text, name text, brand text, compat jsonb, error text)
  join rv_private.store_frontier_v1 f on f.store_id = store and f.url = x.url and f.lease = tok
  where x.error is null and x.page_sha256 ~ '^[0-9a-f]{64}$'
  on conflict do nothing;
  get diagnostics n = row_count;
  update rv_private.store_frontier_v1 f
     set state = case when x.error is null then 'done' else 'failed' end,
         last_error = left(x.error, 200), fetched_at = now(), lease = null, lease_until = null
    from jsonb_to_recordset(rows) as x(url text, error text)
   where f.store_id = store and f.url = x.url and f.lease = tok;
  get diagnostics d = row_count;
  return jsonb_build_object('staged', n, 'frontier_updated', d);
end;
$fn$;

revoke all on function public.rv_store_config() from public, anon, authenticated;
revoke all on function public.rv_store_frontier(text, jsonb, boolean) from public, anon, authenticated;
revoke all on function public.rv_store_claim(text, integer) from public, anon, authenticated;
revoke all on function public.rv_store_stage(text, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.rv_store_config() to service_role;
grant execute on function public.rv_store_frontier(text, jsonb, boolean) to service_role;
grant execute on function public.rv_store_claim(text, integer) to service_role;
grant execute on function public.rv_store_stage(text, uuid, jsonb) to service_role;

-- Publisher --------------------------------------------------------------------
create or replace function rv_private.publish_store_identities_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare r record; mid uuid; pid uuid; ev uuid; made integer := 0; linked integer := 0; held integer := 0;
begin
  if not exists (select 1 from rv_private.factory_controls where enabled)
     or not exists (select 1 from rv_private.verification_control where enabled and auto_publish)
  then return '{"disabled":true}'::jsonb; end if;
  if not pg_try_advisory_xact_lock(741920613::bigint) then return '{"busy":true}'::jsonb; end if;

  for r in
    select p.*, s.publisher, s.brand_allowlist, s.source_id, s.authority
    from rv_private.store_products_v1 p
    join rv_private.store_sources_v1 s on s.id = p.store_id and s.enabled and s.review_state = 'reviewed'
    join rv_private.sources src on src.id = s.source_id
     and src.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
    where p.status = 'staged'
    order by p.staged_at
    limit 1000
  loop
    if r.authority <> 'manufacturer' then
      update rv_private.store_products_v1 set status='held', hold_reason='distributor store: identities need the attributed lane'
       where store_id=r.store_id and url=r.url and page_sha256=r.page_sha256;
      held := held + 1; continue;
    end if;
    if coalesce(r.sku,'') !~ '^[A-Za-z0-9][A-Za-z0-9./-]{2,39}$' or length(coalesce(btrim(r.name),'')) < 3 then
      update rv_private.store_products_v1 set status='held', hold_reason='missing or malformed SKU/name'
       where store_id=r.store_id and url=r.url and page_sha256=r.page_sha256;
      held := held + 1; continue;
    end if;
    if not exists (select 1 from unnest(r.brand_allowlist) b where lower(regexp_replace(coalesce(r.brand,''),'[^A-Za-z ]','','g')) = lower(b)) then
      update rv_private.store_products_v1 set status='held', hold_reason='brand outside the maker''s own brands: '||coalesce(r.brand,'(none)')
       where store_id=r.store_id and url=r.url and page_sha256=r.page_sha256;
      held := held + 1; continue;
    end if;

    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.url, r.page_sha256, r.url, 1, '', 'product page SKU',
            left('SKU #: '||r.sku||' | '||r.name||coalesce(' | Brand: '||r.brand,''), 300),
            r.page_sha256, 'sha256-html-page', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev;
    if ev is null then
      select id into ev from rv_private.evidence
       where source_id = r.source_id and source_record_key = r.url and document_version = r.page_sha256;
    end if;

    select id into mid from rv_private.manufacturers where name = r.publisher;
    select id into pid from rv_private.parts where manufacturer_id = mid and exact_number = upper(r.sku) and variant = '';
    if pid is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (mid, upper(r.sku), '', left(btrim(regexp_replace(r.name, '\s*#\s*'||r.sku||'\s*$', '', 'i')), 200),
              case when r.name ~* 'awning|slide topper|canopy' then 'external_equipment'
                   when r.name ~* 'axle|suspension|hanger|equalizer|leaf spring|brake|hub|bearing|tire|wheel|coupler|hitch|jack|landing gear|stabili' then 'running_gear'
                   when r.name ~* 'window|door|entry|lock|latch|screen|vent cover' then 'windows_doors'
                   when r.name ~* 'toilet|sanitation|waste|black tank|grey tank|gray tank' then 'sanitation'
                   when r.name ~* 'water|pump|faucet|shower|tank|hose' then 'water'
                   when r.name ~* 'furnace|heater|fireplace|heat ' then 'heating'
                   when r.name ~* 'refrigerator|fridge|freezer' then 'refrigeration'
                   when r.name ~* 'trim|molding|moulding|panel|step cover|decal|corner' then 'body_trim'
                   else 'external_equipment' end,
              'published')
      returning id into pid;
      made := made + 1;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_store_identity_publish', pid, r.publisher||' own online store product page; evidence '||ev::text);
    else
      linked := linked + 1;
    end if;
    insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (pid, ev, 'store-reader-v1') on conflict do nothing;
    update rv_private.store_products_v1 set status='published', part_id=pid
     where store_id=r.store_id and url=r.url and page_sha256=r.page_sha256;
  end loop;
  return jsonb_build_object('new_parts', made, 'existing_parts_evidenced', linked, 'held', held);
end;
$fn$;
revoke all on function rv_private.publish_store_identities_v1() from public, anon, authenticated;

select cron.schedule('rv-store-identities-v1', '1-56/5 * * * *', 'select rv_private.publish_store_identities_v1()');

insert into rv_private.camper_input_change_log_v1(actor, change_category, reason, details, rollback_instructions)
values ('ClaudeL', 'store_lane',
  'Store reader lane: read makers'' own online parts stores (first: Lippert) — most RV component part numbers are published there, not in PDFs (Larry, blanket approval 26 Nov 2026)',
  jsonb_build_object('first_store','lippert-store','publication','reviewed store + maker''s own brands + SKU and name only','relationships','staged only'),
  'See header of migration 20261126170000_store_reader_lane_v1.sql');
