-- Drive intake v2 (Larry, 27 Nov 2026 06:08: "boost speed"). Files of one brand share a layout, so
-- runs now claim by brand family (one reader, many files) and by priority (cross-maker links first).
alter table rv_private.drive_intake_v1 add column if not exists priority int not null default 50;
alter table rv_private.drive_intake_v1 add column if not exists family text generated always as (lower(btrim(regexp_replace(split_part(regexp_replace(title, '^\d{2} ', ''), ' - ', 1), '_[0-9]{4}_.*$', '')))) stored;
update rv_private.drive_intake_v1 set priority = case
  when lane = 'aftermarket_xref' then 10
  when lane = 'fitment_guide' then 90
  when lane in ('oem_parts_list','oem_parts_book') and title ~* '(norcold|dometic|thetford|suburban|atwood|hydro ?flame|girard|truma|webasto|eberspacher|seitz|sealand)' then 20
  else 50 end
where status in ('new','needs_split','held');
create or replace function rv_private.claim_drive_intake_v2(p_session text, p_limit int default 4, p_family text default null, p_lane text default null)
returns setof rv_private.drive_intake_v1 language sql as $$
  update rv_private.drive_intake_v1 d set status='claimed', claimed_by=p_session, claimed_at=now(), updated_at=now()
   where d.drive_file_id in (select drive_file_id from rv_private.drive_intake_v1
      where (status='new' or (status='claimed' and claimed_at < now() - interval '3 hours'))
        and (p_family is null or family = lower(p_family)) and (p_lane is null or lane = p_lane)
      order by priority, family, title limit p_limit for update skip locked)
  returning d.*;
$$;
revoke all on function rv_private.claim_drive_intake_v2(text,int,text,text) from public, anon, authenticated;
create or replace view rv_private.drive_intake_families_v1 as
select family, min(priority) priority, count(*) filter (where status='new') new_files, count(*) filter (where status='done') done_files,
       count(*) filter (where status='held') held_files, min(lane) lane from rv_private.drive_intake_v1 group by family;
revoke all on rv_private.drive_intake_families_v1 from public, anon, authenticated;
