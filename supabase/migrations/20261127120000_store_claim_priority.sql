-- Store frontier: claim likely cross-reference pages first (Larry, 27 Nov 2026: "at least 1000 replacement
-- parts"). Product URLs naming replacement-heavy part types (boards, pumps, igniters, thermostats, elements,
-- seals, valves, motors, "replacement") are fetched before the rest; order is otherwise unchanged.
create or replace function public.rv_store_claim(store text, n integer)
 returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $function$
declare tok uuid := gen_random_uuid(); urls jsonb;
begin
  with c as (
    select url from rv_private.store_frontier_v1
     where store_id = store
       and (state = 'pending'
            or (state = 'failed' and attempts < 3 and coalesce(fetched_at, first_seen) < now() - interval '1 hour')
            or (state = 'leased' and lease_until < now()))
     order by state,
              (url !~* '(board|pump|ignit|igniter|thermostat|element|seal|valve|motor|replacement|replaces|module|relay|thermistor|sensor|switch|control|mc/|gasket|regulator|fan|blower|door|latch)'),
              first_seen, url
     limit least(greatest(n,1), 200)
     for update skip locked)
  update rv_private.store_frontier_v1 f
     set state = 'leased', lease = tok, lease_until = now() + interval '30 minutes', attempts = f.attempts + 1
    from c where f.store_id = store and f.url = c.url;
  select coalesce(jsonb_agg(url), '[]'::jsonb) into urls from rv_private.store_frontier_v1 where store_id = store and lease = tok;
  return jsonb_build_object('lease', tok, 'urls', urls);
end;
$function$;
