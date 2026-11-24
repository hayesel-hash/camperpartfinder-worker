
alter table rv_private.camper_input_worklist_v1
 add column if not exists priority_score bigint not null default 0;
alter table rv_private.camper_input_worklist_v1
 add column if not exists priority_reason text;
create or replace function rv_private.camper_refresh_source_priorities_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare n integer;
begin
if not pg_try_advisory_xact_lock(741920975::bigint) then return '{"busy":true}'::jsonb; end if;
with choices as (
  select w.catalogue_id,w.publisher,w.source_url,w.status,
         k.unlinked_parts,
         row_number() over(partition by w.publisher order by
           (case when w.source_url ~* '(cross.?reference|interchange|supersess|replacement|spare.?parts|parts.?list)' then 1 else 0 end) desc,
           w.page_count desc nulls last,w.catalogue_id) as brand_rank
  from rv_private.camper_input_worklist_v1 w
  join rv_private.camper_part_relationship_coverage_v1 k on k.manufacturer=w.publisher
  where w.authority='manufacturer' and w.status <> 'blocked'
), top as (
 select catalogue_id,publisher,unlinked_parts,
 row_number() over (order by unlinked_parts desc,publisher) overall_rank
 from choices where brand_rank=1 and unlinked_parts>0
)
update rv_private.camper_input_worklist_v1 w
set priority_score=case when top.overall_rank<=10 then top.unlinked_parts else 0 end,
    priority_reason=case when top.overall_rank<=10 then
    'Top-10 priority to investigate explicit replacement and cross-reference material for '
    ||top.publisher||' ('||top.unlinked_parts::text||' currently unlinked published parts); existing catalogue alone is not evidence of interchange'
     else null end,
    updated_at=now()
from (select w.catalogue_id,top.overall_rank,top.unlinked_parts,top.publisher
      from rv_private.camper_input_worklist_v1 w
      left join top on top.catalogue_id=w.catalogue_id) top
where top.catalogue_id=w.catalogue_id;
get diagnostics n=row_count;
return jsonb_build_object('worklist_rows_scored',n);
end $fn$;
revoke all on function rv_private.camper_refresh_source_priorities_v1() from public,anon,authenticated;
select cron.schedule('rv-playbook-source-priorities-v1','13 */6 * * *',
'select rv_private.camper_refresh_source_priorities_v1()');
insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values ('ChatGPT','source_prioritisation',
'Score one existing registered source per linked-coverage-deficient manufacturer; do not infer relationships, requeue exhausted PDFs, or bypass access restrictions',
jsonb_build_object('scope','read-only priority planning plus worklist scores',
'missing_official_sources','HWH, Splendide and Aqua-Hot have unlinked parts but no eligible ready catalogue in the worklist'),
'Disable the priority cron; reset scores to zero if reverting. Existing source and part records remain unchanged.');
