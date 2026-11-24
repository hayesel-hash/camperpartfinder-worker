-- Stop advance_catalogue_previews requeueing real extractions forever.
--
-- The job is meant to reprocess historical preview-only batches once. It
-- recognised real extraction only by extraction_version in
-- ('actual-extraction-v1','adaptive-yield-v2'), but the worker now stamps
-- 'adaptive-yield-v6' and rewrites result without the preview_requeued flag.
-- So every completed batch of a manufacturer catalogue still on adapter
-- layout-preview-v1 was requeued every 5 minutes with attempts reset to 0
-- (AL-KO 41-page manual, 3 batches, re-read continuously on 24 Nov), taking
-- worker slots ahead of queued Norcold and Thetford parts lists.
-- Historical preview-only results carry no extraction_version, so that is now
-- the test. Everything else is unchanged.
-- Rollback: re-apply the previous definition (version list
-- 'actual-extraction-v1','adaptive-yield-v2').

create or replace function rv_private.advance_catalogue_previews()
 returns jsonb
 language plpgsql
 set search_path to 'pg_catalog'
as $function$
declare n int; k int;
begin
if not exists(select 1 from rv_private.factory_controls where enabled) then return '{"disabled":true}'::jsonb;end if;
if not pg_try_advisory_xact_lock(741920696::bigint) then return '{"busy":true}'::jsonb;end if;
-- Reprocess historical preview-only batches once, independently of publication authority.
-- Preserve all original observations and source provenance, and skip active leases.
-- A batch with any extraction_version has already had real extraction.
with picked as (
select b.catalogue_id,b.sha256,b.page_start from rv_private.master_catalogue_batches b
join rv_private.master_catalogues c on c.id=b.catalogue_id and c.sha256=b.sha256
where c.state='ready' and c.adapter='layout-preview-v1' and rv_private.catalogue_eligible(c.url)
and b.state='complete' and b.result->>'extraction_version' is null
and b.result->>'preview_requeued' is distinct from 'true'
and b.result ? 'layout_preview'
order by c.pages desc nulls last,b.page_start for update of b skip locked limit 500
)
update rv_private.master_catalogue_batches b set state='queued',attempts=0,next_attempt=now(),lease=null,lease_until=null,
result=b.result||jsonb_build_object('preview_requeued',true,'previous_phase','layout-preview'),
verification_result=jsonb_build_object('status','extraction_pending','reason','preview is not ingestion')
from picked p where b.catalogue_id=p.catalogue_id and b.sha256=p.sha256 and b.page_start=p.page_start;
get diagnostics n=row_count;
-- Convert an entire eligible preview family to real extraction only once all historical
-- preview batches have been requeued or extracted. For third-party sources this remains staging-only.
update rv_private.master_catalogues c set adapter='adaptive-table-v3'
where c.adapter='layout-preview-v1' and c.state='ready' and rv_private.catalogue_eligible(c.url)
and c.authority='distributor'
and not exists(select 1 from rv_private.master_catalogue_batches b where b.catalogue_id=c.id and b.sha256=c.sha256 and b.state='complete' and b.result->>'extraction_version' is null and b.result->>'preview_requeued' is distinct from 'true' and b.result ? 'layout_preview');
get diagnostics k=row_count;
return jsonb_build_object('historical_batches_requeued',n,'archive_adapters_advanced',k);
end $function$;
