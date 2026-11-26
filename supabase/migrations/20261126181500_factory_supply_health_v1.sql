-- One-row supply health summary for the daily starvation check (scheduled task).
-- The factory went 36 hours without new parts (25-26 Nov 2026) because it had
-- finished every registered source and nothing said so. Read-only view.
create or replace view rv_private.factory_supply_health_v1 as
select
  now() as checked_at,
  (select max(inserted_at) from rv_private.part_insert_ledger) as last_part_insert,
  (select count(*) from rv_private.part_insert_ledger where inserted_at > now() - interval '24 hours') as parts_inserted_24h,
  (select count(*) from rv_private.parts where state = 'published') as parts_published,
  (select count(*) from rv_private.relationship_claims where state = 'verified') as verified_relationships,
  (select count(*) from rv_private.master_catalogues where state in ('queued','leased','retry')) as catalogues_waiting,
  (select count(*) from rv_private.master_catalogue_batches where state = 'queued') as batches_queued,
  (select count(*) from rv_private.store_frontier_v1 where state in ('pending','failed','leased')) as store_pages_waiting,
  (select count(*) from rv_private.store_products_v1 where status = 'staged') as store_products_staged,
  (select count(*) from rv_private.aftermarket_assertions_v1 where status = 'staged' and relation = 'replaces') as aftermarket_rows_waiting,
  (select count(*) from rv_private.store_sources_v1 where enabled and review_state <> 'reviewed') as stores_awaiting_review,
  (select count(*) from rv_private.aftermarket_source_pages_v1 where review_state = 'unreviewed') as aftermarket_pages_awaiting_review;
