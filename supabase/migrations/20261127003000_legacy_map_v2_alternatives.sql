-- Legacy-map publisher v2: a row may name stated alternatives for the same obsolete part
-- (Norcold 1200 obsolete-door tables: "first replacement part # is without flapper, the second
-- number is with flapper"). The never-contradict rule still holds a row when the obsolete part
-- already has a verified successor that is NOT one of that row's declared alternatives.
do $do$
declare d text;
  o text := $o$and z.kind in ('replacement','supersession') and z.replacement_part_id <> cp) then$o$;
  n text := $n$and z.kind in ('replacement','supersession') and z.replacement_part_id <> cp
                and not (coalesce(r.qualifiers->'alternatives','[]'::jsonb) ? (select zp.exact_number from rv_private.parts zp where zp.id = z.replacement_part_id))) then$n$;
begin
  d := pg_get_functiondef('rv_private.publish_legacy_number_map_v2(text)'::regprocedure);
  if position(o in d) = 0 then raise exception 'contradiction check not found'; end if;
  execute replace(d, o, n);
end
$do$;
revoke all on function rv_private.publish_legacy_number_map_v2(text) from public, anon, authenticated;
