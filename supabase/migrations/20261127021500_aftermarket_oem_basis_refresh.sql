-- Follow-ups to the loosened OEM-identity rule (20261127020000):
-- 1. record the OEM catalogue variants on every claim whose OEM identity is still only "named in an
--    aftermarket document" (not just on the claim that created the part);
-- 2. refresh restrictions.oem_identity_basis hourly: once the OEM's own catalogue (or any other source)
--    evidences a part that was created from an aftermarket statement, its claims flip to 'oem_catalogue'.
do $do$
declare d text; f text;
  o text := $o$'oem_catalogue_variants', case when m.outcome = 'create' then$o$;
  n text := $n$'oem_catalogue_variants', case when basis = 'named_in_aftermarket_document' then$n$;
begin
  foreach f in array array['rv_private.publish_aftermarket_pdf_v2()', 'rv_private.publish_aftermarket_replacements_v2()'] loop
    d := pg_get_functiondef(f::regprocedure);
    if position(o in d) = 0 then raise exception 'variants line not found in %', f; end if;
    execute replace(d, o, n);
  end loop;
end
$do$;

create or replace function rv_private.refresh_aftermarket_oem_basis_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare confirmed integer; variants integer;
begin
  with u as (
    update rv_private.relationship_claims c
       set restrictions = c.restrictions || jsonb_build_object('oem_identity_basis', 'oem_catalogue', 'oem_identity_confirmed_at', now())
     where c.kind = 'aftermarket_replacement' and c.state = 'verified'
       and c.restrictions->>'oem_identity_basis' = 'named_in_aftermarket_document'
       and rv_private.aftermarket_oem_basis_v1(c.original_part_id) = 'oem_catalogue'
    returning c.id)
  select count(*) into confirmed from u;
  with u as (
    update rv_private.relationship_claims c
       set restrictions = c.restrictions || jsonb_build_object('oem_catalogue_variants',
             to_jsonb(rv_private.aftermarket_oem_variants_v1(c.restrictions->>'oem_brand', p.exact_number)))
      from rv_private.parts p
     where p.id = c.original_part_id and c.kind = 'aftermarket_replacement' and c.state = 'verified'
       and c.restrictions->>'oem_identity_basis' = 'named_in_aftermarket_document'
       and coalesce(c.restrictions->'oem_catalogue_variants', '[]'::jsonb)
           is distinct from to_jsonb(rv_private.aftermarket_oem_variants_v1(c.restrictions->>'oem_brand', p.exact_number))
    returning c.id)
  select count(*) into variants from u;
  return jsonb_build_object('confirmed_by_oem_catalogue', confirmed, 'variant_lists_updated', variants);
end;
$fn$;
revoke all on function rv_private.refresh_aftermarket_oem_basis_v1() from public, anon, authenticated;

select cron.schedule('rv-aftermarket-oem-basis-refresh', '23 * * * *', $$select rv_private.refresh_aftermarket_oem_basis_v1()$$);
