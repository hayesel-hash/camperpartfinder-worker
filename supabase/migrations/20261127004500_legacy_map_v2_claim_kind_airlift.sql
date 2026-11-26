-- Legacy-map publisher v2: the reviewed document may set the claim kind (default supersession).
-- First use: Air Lift "Replacement Air Springs" guide, kit number -> replacement air spring kit.
-- That is a component-level replacement (the air spring inside the kit), recorded as kind
-- 'replacement' with restrictions.scope = 'component_service_part' and a note that the spring
-- kit does not replace the whole suspension kit. Pairs where the kit and spring numbers are the
-- same are not staged.
alter table rv_private.legacy_map_documents_v1 add column if not exists claim_kind text
  check (claim_kind is null or claim_kind in ('supersession','replacement'));

insert into rv_private.manufacturers(name) values ('Air Lift') on conflict (name) do nothing;
insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('airlift-replacement-air-springs-guide', 'Air Lift Company',
        'https://digital.airliftcompany.com/m/368cc2d3f8d21b5b/original/Replacement-Air-Springs-Guide.pdf', 'PUBLIC_FACTS',
        jsonb_build_object('kind','manufacturer_service_part_chart','format','pdf',
          'scope','Air Lift Replacement Air Springs guide (catalogue page 38): kit number -> replacement air spring kit, Air Lift and Air Lift ProSeries',
          'supplied_via','Larry''s Drive folder (ChatGPT handoff, 26 Nov 2026)','approvedBy','Larry, 26 Nov 2026 (blanket approval)'))
on conflict (id) do nothing;

do $do$
declare d text;
  o1 text := $o$values (lp, cp, ev, 'supersession', 'manufacturer', 'verified',$o$;
  n1 text := $n$values (lp, cp, ev, coalesce(d.claim_kind, 'supersession'), 'manufacturer', 'verified',$n$;
  o2 text := $o$and z.kind = 'supersession' and z.state = 'verified') then$o$;
  n2 text := $n$and z.kind = coalesce(d.claim_kind, 'supersession') and z.state = 'verified') then$n$;
begin
  d := pg_get_functiondef('rv_private.publish_legacy_number_map_v2(text)'::regprocedure);
  if position(o1 in d) = 0 or position(o2 in d) = 0 then raise exception 'claim kind lines not found'; end if;
  execute replace(replace(d, o1, n1), o2, n2);
end
$do$;
revoke all on function rv_private.publish_legacy_number_map_v2(text) from public, anon, authenticated;
