-- Non-destructive scheduled pilot: serverless source-page reading independent of GitHub.
create table if not exists rv_private.camper_range_pilot_dispatch_v1(
 request_id bigint primary key,
 sent_at timestamptz not null default now()
);
revoke all on rv_private.camper_range_pilot_dispatch_v1 from public,anon,authenticated;
create or replace function rv_private.camper_dispatch_range_pilot_v1()
returns bigint language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare r bigint;
begin
 if not pg_try_advisory_xact_lock(741920989::bigint) then return null;end if;
 if not exists(select 1 from rv_private.factory_controls where enabled) then return null;end if;
 if exists(select 1 from rv_private.camper_range_pilot_dispatch_v1
   where sent_at>now()-interval '75 seconds') then return null;end if;
 if not exists(select 1 from rv_private.camper_range_pilot_sources_v1
   where enabled and state='queued' and next_attempt<=now()) then return null;end if;
 r:=net.http_post(
  url:='https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-range-reader-pilot',
  headers:=jsonb_build_object('Content-Type','application/json',
  'x-rv-runner',(select decrypted_secret from vault.decrypted_secrets
   where name='rv_factory_runner_v1')),
  body:='{}'::jsonb,
  timeout_milliseconds:=260000
 );
 insert into rv_private.camper_range_pilot_dispatch_v1(request_id) values(r);
 return r;
end $fn$;
revoke all on function rv_private.camper_dispatch_range_pilot_v1()
 from public,anon,authenticated;
select cron.schedule('rv-three-page-range-pilot-v1','* * * * *',
 'select rv_private.camper_dispatch_range_pilot_v1()');
insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
values ('ChatGPT','serverless_range_pilot_schedule',
 'Enable 1-minute controlled 3-page source-reader pilot for one previously approved 2-page Dometic PDF, independent from GitHub Actions. No part publication.',
 jsonb_build_object('pilot_reader','rv-range-reader-pilot','source_limit',1,
 'target','nonzero serverless pages read'),
 'Unschedule rv-three-page-range-pilot-v1 using cron.unschedule(jobid); disable camper_range_pilot_sources_v1; keep source page and event history.');
