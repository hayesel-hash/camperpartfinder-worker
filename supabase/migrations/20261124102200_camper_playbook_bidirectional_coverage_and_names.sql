
-- Manufacturer coverage measures both endpoints of documented relationships.
create or replace view rv_private.camper_part_relationship_coverage_v1
with (security_invoker=true) as
with linked as (
 select original_part_id id from rv_private.relationship_claims
 where state='verified' and kind in ('replacement','supersession')
 union
 select replacement_part_id id from rv_private.relationship_claims
 where state='verified' and kind in ('replacement','supersession')
), brand_counts as (
 select m.name manufacturer,count(*)::bigint published_parts,
 count(*) filter(where l.id is not null)::bigint related_parts,
 count(*) filter(where l.id is null)::bigint unlinked_parts,
 count(*) filter(where p.name is null or btrim(p.name)='' or
 p.name ~* '^(part|spare part|superseded part)')::bigint placeholder_named
 from rv_private.parts p join rv_private.manufacturers m on m.id=p.manufacturer_id
 left join linked l on l.id=p.id
 where p.state='published'
 group by m.name
)
select manufacturer,published_parts,related_parts,unlinked_parts,placeholder_named,
 round(100.0*related_parts/nullif(published_parts,0),3) percent_documented_relationship_coverage,
 (related_parts>0) has_any_verified_relationship
from brand_counts;
revoke all on rv_private.camper_part_relationship_coverage_v1 from public,anon,authenticated;

-- Only index numbers already observed in published PDFs. This is not a raw
-- full-page token index and cannot by itself verify source name alignment.
create or replace view rv_private.camper_observed_name_sources_v1
with (security_invoker=true) as
select c.publisher,c.authority,c.id catalogue_id,c.url,c.sha256,
o.number part_number,o.description proposed_name,o.page,o.position,o.extraction_method,o.state,
case when o.description is null or btrim(o.description)='' then 'no_name'
 when o.description ~* '^(replaces|replacement for|supersedes|superseded by|for:|uses:|see:|interchange|part|qty|ref|oem|model)$' then 'reject_index_or_heading'
 when o.description ~ '[[:alpha:]]{3}' then 'candidate_requires_page_review'
 else 'reject_ambiguous' end name_quality_state
from rv_private.master_catalogue_observations o
join rv_private.master_catalogues c on c.id=o.catalogue_id and c.sha256=o.sha256
where o.number ~ '[0-9]' and c.state='ready';
revoke all on rv_private.camper_observed_name_sources_v1 from public,anon,authenticated;

insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values('ChatGPT','coverage_and_name_diagnostics',
'Measure relationship coverage on both original and replacement sides and expose attributed names from already extracted catalogue observations; never infer fitment or promote unreviewed names',
jsonb_build_object('new_views',jsonb_build_array('camper_part_relationship_coverage_v1','camper_observed_name_sources_v1'),
'raw_page_token_index_not_yet_implemented',true),
'Drop these read-only diagnostic views if necessary; no published records have changed.');
