-- CamperMatch publication and extraction diagnostics, adapted from the marine
-- bpf_publication_funnel_v4 and bpf_extraction_yield_by_manufacturer_v1.
-- Read-only: does not change authority, publish any parts, or requeue jobs.
create or replace view rv_private.camper_catalogue_pipeline_funnel_v1
with (security_invoker=true)
as
with observations as (
  select catalogue_id,sha256,
     count(*)::bigint as observed_rows,
     count(*) filter (where state='staged')::bigint as staged_rows,
     count(*) filter (where state='published')::bigint as published_rows,
     count(*) filter (where description is not null)::bigint as described_rows,
     count(*) filter (where extraction_method='labelled-column-v1')::bigint as labelled_rows,
     count(*) filter (where extraction_method='synthesised-layout-v5')::bigint as synthetic_layout_rows,
     count(distinct number)::bigint as observed_unique_numbers
  from rv_private.master_catalogue_observations
  group by catalogue_id,sha256
), batches as (
  select catalogue_id,sha256,
    count(*)::bigint as total_batches,
    count(*) filter(where state='complete')::bigint as completed_batches,
    count(*) filter(where state='held')::bigint as held_batches,
    count(*) filter(where state in ('queued','retry','leased'))::bigint as unfinished_batches,
    count(*) filter(where state='complete' and coalesce((result->>'extracted')::integer,0)=0)::bigint as zero_extraction_batches
  from rv_private.master_catalogue_batches
  group by catalogue_id,sha256
), relationships as (
  select catalogue_id,sha256,
    count(*)::bigint as relationship_candidates,
    count(*) filter(where verification_state='candidate')::bigint as pending_relationships
  from rv_private.catalogue_relationship_candidates_v1
  group by catalogue_id,sha256
)
select
 c.id as catalogue_id,c.publisher,c.authority,c.adapter,c.url,c.state as document_state,
 c.pages as document_pages,c.created_at,
 coalesce(b.total_batches,0)::bigint total_batches,
 coalesce(b.completed_batches,0)::bigint completed_batches,
 coalesce(b.held_batches,0)::bigint held_batches,
 coalesce(b.unfinished_batches,0)::bigint unfinished_batches,
 coalesce(b.zero_extraction_batches,0)::bigint zero_extraction_batches,
 coalesce(o.observed_rows,0)::bigint observed_rows,
 coalesce(o.observed_unique_numbers,0)::bigint observed_unique_numbers,
 coalesce(o.described_rows,0)::bigint described_rows,
 coalesce(o.staged_rows,0)::bigint staged_rows,
 coalesce(o.published_rows,0)::bigint published_rows,
 coalesce(o.labelled_rows,0)::bigint labelled_rows,
 coalesce(o.synthetic_layout_rows,0)::bigint synthetic_layout_rows,
 coalesce(r.relationship_candidates,0)::bigint relationship_candidates,
 coalesce(r.pending_relationships,0)::bigint pending_relationships,
 case
  when c.state='held' then 'document_blocked_or_policy'
  when coalesce(b.unfinished_batches,0)>0 then 'extraction_queued'
  when coalesce(b.held_batches,0)>0 then 'held_batches_require_classification'
  when coalesce(b.completed_batches,0)=0 then 'document_not_processed'
  when coalesce(o.observed_rows,0)=0 then 'completed_without_identities'
  when coalesce(o.staged_rows,0)>0 then 'staged_not_fully_published'
  when coalesce(r.relationship_candidates,0)>0 and coalesce(r.pending_relationships,0)>0 then 'relationship_candidates_need_verification'
  else 'processed_awaiting_unique_yield_assessment'
 end as diagnostic_stage
from rv_private.master_catalogues c
left join observations o on o.catalogue_id=c.id and o.sha256=c.sha256
left join batches b on b.catalogue_id=c.id and b.sha256=c.sha256
left join relationships r on r.catalogue_id=c.id and r.sha256=c.sha256;
revoke all on rv_private.camper_catalogue_pipeline_funnel_v1 from public,anon,authenticated;

create or replace view rv_private.camper_manufacturer_yield_v1
with (security_invoker=true)
as
select publisher,authority,
 count(*)::bigint catalogues,
 sum(completed_batches)::bigint completed_batches,
 sum(zero_extraction_batches)::bigint zero_extraction_batches,
 sum(held_batches)::bigint held_batches,
 sum(observed_rows)::bigint observed_rows,
 sum(staged_rows)::bigint staged_rows,
 sum(published_rows)::bigint published_observations_not_unique_parts,
 sum(relationship_candidates)::bigint relationship_candidates,
 sum(pending_relationships)::bigint pending_relationships,
 sum(case when diagnostic_stage='completed_without_identities' then 1 else 0 end)::bigint zero_yield_documents,
 sum(case when diagnostic_stage='staged_not_fully_published' then 1 else 0 end)::bigint publication_backlog_documents
from rv_private.camper_catalogue_pipeline_funnel_v1
group by publisher,authority;
revoke all on rv_private.camper_manufacturer_yield_v1 from public,anon,authenticated;
