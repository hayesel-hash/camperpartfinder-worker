-- Read-only baseline and root-cause diagnostics. SELECT only; safe to run on production.
-- Run each statement separately and save the output before ANY migration or deployment.

-- A. Appendix B baseline -----------------------------------------------------
SELECT count(*) AS published_manufacturer_parts FROM rv_private.parts WHERE state='published';
SELECT count(*) AS published_distributor_identities, count(*) FILTER (WHERE product_description IS NOT NULL) AS described
  FROM rv_private.published_distributor_identities_v1 WHERE publication_state='published';
SELECT * FROM rv_private.relationship_metrics_v1 ORDER BY tick_at DESC LIMIT 1;
SELECT state, count(*) AS batches FROM rv_private.master_catalogue_batches GROUP BY state ORDER BY state;
SELECT * FROM rv_private.reimo_relationship_progress_v2;

-- B. Root cause 1: discovery -> acquisition gap -------------------------------
-- Actions logs 21-22 Nov: 419 repository pages crawled, 6,041 links returned, ZERO manifest (acquire) jobs.
SELECT table_name FROM information_schema.tables WHERE table_schema='rv_private'
  AND table_name ~ '(repositor|frontier|discover|link|candidate|source)' ORDER BY 1;
SELECT authority, adapter, state, count(*) FROM rv_private.master_catalogues GROUP BY 1,2,3 ORDER BY 4 DESC;
SELECT access_state, metadata->>'kind' AS kind, count(*) FROM rv_private.sources GROUP BY 1,2 ORDER BY 3 DESC;

-- C. Root cause 2: control-plane loops -----------------------------------------
-- master-962581697c932eb5d991b177e60a63f9 was re-claimed in every run for ~24 h (149 batches, 0 saved).
SELECT * FROM rv_private.master_catalogues WHERE id='master-962581697c932eb5d991b177e60a63f9';
SELECT * FROM rv_private.master_catalogue_batches WHERE catalogue_id='master-962581697c932eb5d991b177e60a63f9' ORDER BY page_start LIMIT 60;
-- Held backlog by reason (1,521 held in snapshot; 42 Reimo batches held for "unsupported adapter" on 21 Nov).
SELECT result->>'error' AS reason, count(*) FROM rv_private.master_catalogue_batches WHERE state='held' GROUP BY 1 ORDER BY 2 DESC;
-- Every rv-* cron job with its most recent run outcome.
SELECT j.jobid, j.jobname, j.schedule, j.active, d.status, d.start_time, left(d.return_message,160) AS last_message, j.command
  FROM cron.job j
  LEFT JOIN LATERAL (SELECT * FROM cron.job_run_details r WHERE r.jobid=j.jobid ORDER BY r.start_time DESC LIMIT 1) d ON true
 WHERE j.jobname LIKE 'rv-%' ORDER BY j.jobname;
-- Which cron commands write master_catalogue_batches.state (candidates for the re-queue loop).
SELECT jobname, schedule, command FROM cron.job WHERE command ~* '(batch|requeue|retry|reset|release|replay)' ORDER BY jobname;

-- D. Root cause 3: relationship extraction and verification -------------------
SELECT column_name, data_type, table_name FROM information_schema.columns
 WHERE table_schema='rv_private' AND table_name IN ('relationship_claims','catalogue_relationship_candidates_v1','verified_replacements_v1')
 ORDER BY table_name, ordinal_position;
-- Share of staged replacement claims whose page was flagged "qualified" by the page-level regex
-- (v1 flags any page containing kit/only/if/note/serial/*).
SELECT pg_get_viewdef('rv_private.verified_replacements_v1'::regclass, true);
SELECT pg_get_viewdef('rv_private.relationship_metrics_v1'::regclass, true);

-- E. Unversioned production logic -----------------------------------------------
-- Repo contains ONE migration. Everything below that is not in Git is unreviewed production code.
SELECT n.nspname, p.proname, md5(pg_get_functiondef(p.oid)) AS def_md5, length(pg_get_functiondef(p.oid)) AS def_len
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname IN ('rv_private','public') AND p.prokind='f' ORDER BY 1,2;
SELECT schemaname, viewname FROM pg_views WHERE schemaname='rv_private' ORDER BY 2;

-- F. Silent identity drops in publish_generic_master_identities ------------------
-- Publication requires extraction_method='labelled-column-v1' AND position '... colN'.
-- labelled_card_rows / explicit_inline_rows emit 'labelled-column-v1' WITHOUT col -> never published.
SELECT extraction_method, (position ~ '^x[0-9]+ y[0-9]+ col[0-9]+$') AS publishable_position, state, count(*)
  FROM rv_private.master_catalogue_observations GROUP BY 1,2,3 ORDER BY 4 DESC;
