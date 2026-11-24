-- RV evidence classification rule adopted 2026-11-24.
-- The maker of an aftermarket replacement is authoritative for its own
-- explicit assertion; that does not imply endorsement by the OEM.
-- A seller/distributor is never silently promoted to manufacturer authority.
create or replace function rv_private.classify_crossref_publisher_v1(
    p_publisher_role text,
    p_claim_issuer text,
    p_replacement_brand text,
    p_explicit_replacement boolean,
    p_provenance_complete boolean
)
returns text
language sql immutable set search_path to pg_catalog
as $fn$
select case
 when not coalesce(p_explicit_replacement,false)
      or not coalesce(p_provenance_complete,false)
      or nullif(btrim(coalesce(p_claim_issuer,'')),'') is null
 then 'insufficient_evidence'
 when lower(btrim(coalesce(p_publisher_role,''))) in
      ('manufacturer','aftermarket_manufacturer','replacement_manufacturer')
      and nullif(btrim(coalesce(p_replacement_brand,'')),'') is not null
      and lower(btrim(p_claim_issuer))=lower(btrim(p_replacement_brand))
 then 'manufacturer_certified_aftermarket_claim'
 when lower(btrim(coalesce(p_publisher_role,''))) in
      ('distributor','retailer','dealer','reseller','aftermarket_distributor')
 then 'attributed_distributor_claim'
 else 'requires_source_role_review'
 end
$fn$;
comment on function rv_private.classify_crossref_publisher_v1(text,text,text,boolean,boolean)
is 'Manufacturer of the offered aftermarket replacement can certify its own explicit replacement claim, with provenance; no OEM endorsement implied. Distributor assertions remain attributed, lower certainty. Never infer replacement from fitment or transitive association. Only a classifier, not permission to automatically publish.';
revoke all on function rv_private.classify_crossref_publisher_v1(text,text,text,boolean,boolean)
from public,anon,authenticated;
insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values('ChatGPT','crossref_authority_policy',
'Apply user-approved provenance distinction between aftermarket maker and distributor claims; no automatic publication or old relationship reclassification',
jsonb_build_object('aftermarket_maker','explicit self-authored maker claim is manufacturer certified for that maker, not OEM endorsed','distributor','lower-confidence attributed claim','fitment','not interchangeability','publication','not wired into unreviewed auto-publish'),
'Drop classify_crossref_publisher_v1 if reverting; no product or relationship rows were changed.');
