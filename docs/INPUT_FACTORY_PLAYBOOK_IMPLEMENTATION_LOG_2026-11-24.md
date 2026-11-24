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


## 2026-11-24 17:38–17:52 UTC: CamperMatch fix-plan implementation

Source: user-supplied *CamperPartMatch: why the factory is stuck, and the fix plan* (24 Nov 2026). This is the work-order execution record, not a claim that all six work orders are complete.

### WO-1: GitHub billing and production restart
- User made `hayesel-hash/camperpartfinder-worker` public. Verified via GitHub API: `private=false`, `visibility=public`.
- GitHub Actions dispatcher and one earlier six-job matrix started after billing/visibility fix.
- The 17:32 matrix failed in *all* six workers on `scripts/catalogue_relationship_extractor.py` line 260: new explicit OEM-column sample asserted two candidates but received none. The OIDC authentication and PDF packages installed successfully; this was not a billing failure.
- Changed `scripts/catalogue_relationship_extractor.py`: a conservative, page-geometry, header-gated two-column matcher for distributor SKU and OEM number. Stages **unreviewed** evidence only; never promotes an inferred replacement. Regression run `45451228517` passed after fix, and later `45452836579` passed.
- Changed `.github/workflows/rv-runner-capacity.yml`: one recovery matrix is now permitted when a prior executed worker failed on a **different commit** and the current SHA has a successful complete regression. Same failed SHA remains blocked, avoiding infinite paid retries. Bounded wait for regression prevents push-event races.
- Changed `.github/workflows/reimo-extractor-test.yml`: dispatcher workflow edits now also run the full regression.
- Recovery matrix `45452922197` was launched by corrected dispatcher at 17:50 UTC. Five of six workers had completed successfully at the most recent check; `extract-1` was still running. Final quality and throughput had **not** yet been established.
- Separate `rv-range-reader-pilot` serverless Edge Function and database jobs were already deployed concurrently during this work. We inspected, **did not duplicate or rewrite**, that pilot. Observed 17 pages in six successful reading calls and two failed calls at 17:51 UTC. Six Winnebago pages were read in two 3-page requests of ~7.6 seconds each. The 353 MB Reimo document failed PDF.js allocation and was deliberately disabled for serverless use in favour of the disk worker. Raw pages are not verified against a full-document SHA and should not be auto-published.
- Rollback: revert the three GitHub file commits (subject to later concurrent changes). The new dispatcher cannot continuously redispatch a repeatedly failing same SHA.

### WO-2: Existing staged replacement candidate audit
- `catalogue_relationship_candidates_v1` contained nine `fits_model` Reimo candidates and **zero** `distributor_manufacturer_crossref` or `stated_replacement_unverified` candidates.
- `distributor_oem_assertions_v6` contained zero rows. `manufacturer_replacement_assertions_v6` contained zero rows.
- `replacement_candidates` contained 27 already-verified older candidate rows; **not 27 distributor replacements pending publication**.
- Therefore no distributor replacements were promoted. Requires actual pairs with publisher + source/page + original wording, 40 sampled examples at >=90%, and user approval to publish as *attributed unverified distributor claims* (not OEM-certified and never fitment).
- Existing 40 manufacturer-verified edges were joined by two explicit Norcold supersessions at 17:49 UTC (pairs `639569 -> 693298` and `639570 -> 693299`, Thetford-hosted manufacturer parts list PDF p.7; verification version `official-manufacturer-exact-row-manual-20261124-v1`). These were published by a separate manual process while this work was running, **not the newly repaired GitHub worker**. End count: 42.

### WO-3: OEM-column extractor
- Patched and regression-tested the safe column-aware parser, but the 1,100-page Reimo full replay and its >=40 genuine-claim spot-check have **not** been executed. No new distributor relation candidates as of 17:51 UTC. Do not claim the extractor increased real-world relationship yield until measured.

### WO-4: Link-rich source reconnaissance, not yet admission
- **HWH** (7,592 published unlinked): official parts manual PDF `https://www.hwhcorp.com/ml11428-15.pdf` and existing-part/replacement-number quick-reference `https://www.hwhcorp.com/ml11428qr_007.html`; HWH Europe `https://www.hwh-europe.com/download/quickrefjacks.pdf` mainly lists *components* of jacks, which must NOT be mistaken for substitutes for the whole jack. The automated robots check for these hosts is unavailable; do **not** bypass it. Obtain an owner-supplied catalogue via Drive if inaccessible.
- **Winnebago** (3,725): `https://www.winnebago.com/owners/owner-resources/manuals-and-diagrams/supplier-links` identifies OEM suppliers, not automatic equivalence; no cross-reference source yet verified. New independent PDF Range pilot has begun extracting Winnebago pages.
- **Fiamma** (2,945): `https://www.agentfiamma.co.uk/fiamma-awning-spares/` retailer spare-part catalogue; no cross-manufacturer equivalence demonstrated.
- **Dexter** (1,338): `https://loyalaxles.com/resources/trailer-brake-parts-cross-reference/` publishes Dexter/AL-KO/aftermarket comparison table; source authority and robots/terms must be checked before queue admission.
- **Norcold** (1,076 previously unlinked; now two more official pairs): Thetford-hosted Norcold parts lists already source exact supersessions; prioritize OEM cross-reference documents separately.
- **Jokon** (587): `https://quickparts.mobi/store-online-jokon/` retailer claims to identify old/discontinued Jokon references and compatible replacements; no machine-readable pairs verified yet.
- **Thetford** (~524): parts manuals provided 40 verified manufacturer supersessions; aftermarket alternatives require additional retailer-source discovery.
- These are **source leads**, not approved ingestion/crawl permissions. No robots-block bypass or unverified equivalence publication.

### WO-5: Correct misleading name baseline
- The old "only 36 unnamed parts" metric was materially wrong: **7,555 of 7,592 HWH parts** have names of the form `HWH catalogue part APxxxx`. They are placeholders and must be counted as **not cleanly named**.
- Corrected conservative *candidate* clean-name count from SQL excluding generic catalogue-part and empty/placeholder prefixes: **12,677 / 20,268**. Additional Winnebago names are shortened/truncated; therefore this is an **upper-bound heuristic**, not a verified 90%-precision count.
- Only early Winnebago PDF pilot pages available so far: too little to produce and validate a 40-row unique clean-name improvement batch. No existing part names were overwritten.

### Current accepted outcomes
- Github public Actions execution restored.
- Production matrix started successfully with the repaired parser; final result still pending.
- Independent serverless PDF reader demonstrated non-zero pages without Actions, but is still a pilot and not integrated into main publication.
- Manufacturer-verified links increased 40 -> 42 via another process; manufacturer part count remained 20,268.
- **No newly published attributed distributor alternatives and no verified clean-name growth have been demonstrated from these changes yet.**

### Immediate follow-up
1. Check run `45452922197` final 6/6 success and per-run published part and relationship deltas; address any concrete remaining worker error.
2. Allow and inspect actual distributor/OEM candidates after controlled page-range extraction on a sample Reimo PDF, then run a 40-row source-page audit; do not rerun all 1,100 pages blindly.
3. Decide attributed distributor claims publication policy. Preserve distinct authority and relationship kinds.
4. Keep the serverless range pilot operating only on small PDFs it can safely handle; add extraction + evidence quality gates before it becomes production publisher.
5. Obtain official HWH replacement/name manuals via approved access and use them to replace generic placeholder names, tested on >=40 random rows, while explicitly distinguishing jack *components* from jack *replacements*.
