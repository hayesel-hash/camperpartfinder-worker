-- Drive intake register: one row per file supplied in Larry's Google Drive folders, so every
-- ClaudeL session (and the scheduled intake run) can see what is new, who is working on it and
-- what came of it. Claiming is a conditional update on status, so two sessions never take the
-- same file.
create table if not exists rv_private.drive_intake_v1 (
  drive_file_id text primary key,
  folder_id text not null,
  title text not null,
  bytes bigint,
  lane text not null check (lane in ('aftermarket_xref','oem_parts_list','fitment_guide','oem_parts_book','other')),
  status text not null default 'new' check (status in ('new','claimed','done','held','needs_split','skipped')),
  claimed_by text,
  claimed_at timestamptz,
  doc_sha256 text,
  source_id text,
  result jsonb,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table rv_private.drive_intake_v1 enable row level security;
revoke all on rv_private.drive_intake_v1 from public, anon, authenticated;

create or replace function rv_private.claim_drive_intake_v1(p_session text, p_lane text default null, p_limit int default 1)
returns setof rv_private.drive_intake_v1 language sql as $$
  update rv_private.drive_intake_v1 d
     set status='claimed', claimed_by=p_session, claimed_at=now(), updated_at=now()
   where d.drive_file_id in (
     select drive_file_id from rv_private.drive_intake_v1
      where (status='new' or (status='claimed' and claimed_at < now() - interval '3 hours'))
        and (p_lane is null or lane = p_lane)
      order by case lane when 'aftermarket_xref' then 0 when 'oem_parts_list' then 1 when 'oem_parts_book' then 2 else 3 end, title
      limit p_limit for update skip locked)
  returning d.*;
$$;
revoke all on function rv_private.claim_drive_intake_v1(text,text,int) from public, anon, authenticated;
-- Seed (53 files in "CamperPartMatch — 20 Aftermarket Parts Catalogues for Claude",
-- Drive folder 1VPv8yDVJFuSmUaHzpwuXBYB1inByelsy) was inserted by hand on 26 Nov 2026.
