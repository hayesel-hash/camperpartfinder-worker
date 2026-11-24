# CamperPartMatch input factory — engineering log

## 2026-11-24: BoatPartMatch playbook implementation (ChatGPT)

Reference: user-supplied *CamperPartMatch inputs factory: playbook and super prompt*, 24 Nov 2026.

### Production baseline
- Published manufacturer identities: **20,268** (unchanged during this session).
- Verified replacement/supersession edges: **40** (unchanged during this session).
- Published Reimo distributor identities: **8,377**.
- Verified-edge endpoints: **77 unique published parts** of 20,268 (**0.380%**); only Thetford currently has verified relationships. Fifteen manufacturers have zero.
- Registered master catalogues: **1,537**; previously 275 catalogue records held, 1,522 page batches held.
- Caveat: many held page batches are deliberately catalogue-only, not necessarily retries waiting for repair.

### Changes actually deployed (Camper Supabase `dlijhukwzlqwtmiynncg` ONLY)
1. **Auditable catalogue worklist**: `rv_private.camper_input_worklist_v1`, refreshed by `rv-playbook-worklist-sync-v1` every 5 minutes; statuses need_source / reading / read / staged / promoted / blocked; source URL, authority, document SHA, page count, last error and opt-in auto-promote (default false). Current initial sync: 1,537 catalogues (1,019 read, 29 staged, 488 blocked/held, 1 reading). Worklist is currently **observational**; existing acquisition workers do not yet claim directly from it.
2. **Quality review gate**: `rv_private.camper_input_quality_batch_v1` and `camper_input_quality_sample_v1`; >=40 individual reviewed records and >=90% accepted required for the `approved` decision. `camper_finalize_quality_review_v1(label,reviewer)` computes the verdict from row-level reviews. This gate is currently **not integrated with legacy auto-publication functions**, and must not be described as preventing all pre-existing auto-publications.
3. **Initial Jokon cohort**: 50 deterministic staged name observations, batch `jokon-synth-layout-20261124-a`. Text shows long mixed German specifications and uncertain clean name boundaries. Batch deliberately **unreviewed** pending page-alignment verification; no records promoted.
4. **Two-sided verified relation coverage**: `camper_part_relationship_coverage_v1`, counts both originals and replacements and shows zero-link manufacturers. Does not assert transitivity or fitment.
5. **Existing observation name index**: `camper_observed_name_sources_v1`, with publisher, exact PDF, page, SHA, extraction method and candidate name. This is **not** a complete raw-page token index and does not authorise publication.
6. **Top-10 source-priority list**: `camper_refresh_source_priorities_v1()`, scheduled every six hours. Assigns worklist priority scores to registered official catalogues from brands with highest unlinked part counts. Does not automatically reprocess exhausted PDFs or infer interchangeability.
7. **Change ledger**: `camper_input_change_log_v1`, with rationale and rollback instructions.

### Current source priorities
Winnebago (3,725 unlinked), Fiamma (2,945), Dexter (1,338), Norcold (1,076), Jokon (587), Thetford (524), Carefree of Colorado (459), Lippert (439), Truma (384), REMIS (290). HWH (7,592), Splendide (435) and Aqua-Hot (117) need an eligible parts/interchange catalogue discovered and are not in this registered-source-only top ten.

### Critical runtime blocker found
GitHub Actions dispatcher `rv-runner-capacity.yml` has repeated failed scheduled runs on 24 Nov (e.g. 45368931987 at 09:50 UTC, 45359238127 at 08:47, 45350461880 at 07:45). Each failed before any job step began; runner logs are unavailable/404. **Likely GitHub runner provisioning/Actions policy/billing/platform access issue, not proven.** Last successful disk worker run observed 24 Nov 02:28 UTC. Do not blindly retry expensive matrix runs. Confirm account Actions settings, capacity/quotas and runner allocation, then dispatch a controlled worker run and measure actual additions.

### Incomplete vs. playbook
- NO HTTP Range PDF reader / three-page, five-minute page-range service deployed. Existing disk-backed GitHub worker remains the processor.
- NO single central 20-second acquisition tick replacing existing schedulers. Worklist sync is five minutes; legacy schedules have not been disabled.
- NO complete every-page token index: current candidate name index uses extracted observations.
- NO automatic source-page name validation / 50-row x-position multi-column check, and no approved quality sample.
- NO Shopify/affiliate page changes; these belong to the web project, outside this ingestion-worker change.
- NO throughput uplift yet demonstrated; parts and relationship counts did not change during this session.

### Safety and rollback
All changes are additive; existing parts and replacement claims were not deleted or overwritten. No marine database was modified.
Disable only newly added schedules by name to stop new worklist refresh and scoring; preserve tables and the audit log. The new views are read-only; no rollback of published records is necessary.
Do not automatically label distributor cross-references as OEM-certified equivalence or apply transitive fitment.

### Next structural engineering acceptance tests
1. Resolve GitHub Actions pre-run allocation failures without bypassing account controls; test one successful worker invocation.
2. Evaluate remote Range-capable PDF reading with a 3-page bounded batch against a 1,100-page catalogue, verifying actual bytes requested, timeouts, and exact-page text.
3. Wire the quality-approved stage to all applicable publication paths without silently altering existing manufacturer rules; compare 40+ manually page-checked rows per *new* extractor batch before promotion.
4. Add raw-page token indexing and evidence-backed naming recovery; retain manufacturer identity and attributed descriptions separately.
5. Measure *new clean names plus documented relationships* per hour, verified both-side coverage, failures per 20-minute window, and source-specific quality.

## 2026-11-24 evening — controlled factory recovery and results

### GitHub budget / runner recovery
- Repository was changed to **public** by owner; a controlled dispatcher retry succeeded, launching all six GitHub disk-worker jobs (run 45449232188; completed successfully).
- A new x-position-aware extractor for explicitly labelled distributor SKU / OEM columns was added to `scripts/catalogue_relationship_extractor.py`. Synthetic test initially failed on `Art.-Nr.` punctuation; fixed at SHA `7f2ad1074a18a8c4be83c7e13b5636b1442209c1`, with Reimo regression run 45450007868 passing.
- The replacement cross-reference output remains **unreviewed distributor evidence**, not manufacturer certification. No real Reimo batch has been selectively replayed through that extractor yet.
- Exact-current-SHA regression tests are needed before an automatic post-failure worker restart. The Reimo regression workflow now triggers on all main-branch commits, not just Python paths, allowing a corrected commit to satisfy the dispatch circuit breaker.

### Independent serverless reader: deployed and proven, but with a size limit
- Deployed Supabase Edge Function `rv-range-reader-pilot` with existing factory-secret authentication, RFC9309 robots checks, exact approved source selection and serialized HTTP Range requests. Companion code: `supabase/functions/rv-range-reader-pilot/`; migration: `20261124173700_camper_range_pilot_schema.sql`, later fixed stage RPC, and `20261124174000_range_reader_pilot_dispatch.sql`.
- Database-owned cron `rv-three-page-range-pilot-v1` dispatches one bounded three-page claim per minute, without GitHub Actions; stores raw page text and x/y spans only.
- Dometic official PDF: 2 pages saved after 3 Range requests, approximately 3.2 seconds.
- Winnebago official 241-page PDF (~13.25 MB): first two three-page requests succeeded, each using approximately 1.19 MB transferred in 7.7 seconds, rather than downloading the whole source per batch. Additional pages continue through a real database schedule. **Do not count these raw pages as published product identities.**
- Reimo 1,100-page PDF (~353 MB) failed with `Array buffer allocation failed` in Edge PDF.js. It was deliberately disabled and blocked in the pilot; preserve GitHub disk processing for enormous PDFs. Do not claim this Range implementation handles 400 MB.
- PDF page results retain source document identity and page coordinates, but the original whole-file SHA256 is **not independently reverified by Range reads**. They remain staging-only pending integrity and 40-row quality validation.
- A PostgreSQL `chr(0)` issue initially blocked raw page save; fixed by removing the invalid NUL construction. Edge already strips NULs before transport.

### Verified new relationships from existing official manufacturer PDF
- Norcold's official Thetford-hosted *N7/N8 Polar Series Parts List* directly states `639569 SUPERSEDED BY 693298` and `639570 SUPERSEDED BY 693299` on physical PDF page 7.
- Both original and replacement part IDs were already published. Exact source text, SHA256, URL, page, position and manufacturer authority were checked; no conflicting claims.
- Two exact-source supersessions inserted with version `official-manufacturer-exact-row-manual-20261124-v1`, evidence stored in `rv_private.evidence`; SQL review in `database/evidence_reviews/norcold_20261124_verified_page7.sql`.
- Verified edges **40 → 42**; covered published parts (both endpoints) **77 → 81**; coverage **0.380% → 0.400%**; manufacturers with verified edges **1 → 2**.
- No new manufacturer part identities or clean part names were published from the range pilot in this session.

### Outstanding WO-2/3/4/5/6
- Staged distributor-to-OEM replacement assertions remain at **zero**; the existing nine Reimo fitment candidates cannot be misreported as replacements. A 40-source-row check and owner approval are required before publisher-attributed distributor links can be published.
- No real Reimo column-aware extraction yield has been demonstrated yet; run a *versioned, selective* relationship replay, not a destructive reset, then sample >=40 real claims if available.
- Promising link-rich sources identified for review include Dinosaur Electronics' official Dometic/Norcold replacement-board charts, MC Enterprises replacement-parts references, and Dexter Trailer Parts Pro. **Robots and source-rights have not yet been confirmed**, so none should be silently crawled or approved.
- Raw-page token indexing, high-confidence name recovery and full integration of the 40-row review gate with legacy publication are still incomplete. Do not claim they are deployed.
- The old 51 database schedules remain; worklist is observational, not yet the sole controller.

### Rollback and safety
- Stop just the new autonomous Range pilot via `cron.unschedule` on `rv-three-page-range-pilot-v1` and `update rv_private.camper_range_pilot_sources_v1 set enabled=false`; preserve raw pages/events.
- Do not remove or change the marine database, existing released manufacturer parts, or distributor identities.
- If official Norcold supersessions are contradicted, put precisely those claims on hold after reviewing the evidence. Do not erase source/audit records.
