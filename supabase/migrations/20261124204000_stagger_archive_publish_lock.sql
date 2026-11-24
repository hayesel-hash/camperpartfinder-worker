-- rv-generic-master-publish (job 13) and rv-attributed-archive-publish (job 22)
-- share advisory lock 741920612 and both fire at second 0 of every minute.
-- When job 22 wins the race, job 13 returns {"busy":true} immediately; on
-- 24 Nov 20:27-20:32 this left 2,558 staged Winnebago identities unpublished
-- until a manual call. Start job 22 twenty seconds into the minute so the two
-- no longer collide. Mutual exclusion and frequency are unchanged.
-- Rollback: select cron.alter_job(22, command := 'select rv_private.publish_attributed_archive_identities()');
select cron.alter_job(
  (select jobid from cron.job where jobname = 'rv-attributed-archive-publish'),
  command := 'select pg_sleep(20); select rv_private.publish_attributed_archive_identities()'
);
