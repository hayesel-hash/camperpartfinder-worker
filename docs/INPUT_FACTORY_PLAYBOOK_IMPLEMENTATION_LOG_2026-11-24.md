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
