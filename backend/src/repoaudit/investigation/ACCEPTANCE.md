# Issue Investigator — Acceptance Bar (Phase 0 + remaining realtime gaps)

## Success criteria
- ≥80% of golden scenarios that include a stack/route/log isolate the expected file in the top 3 targets.
- Vague description-only reports ("something is broken") return `PARTIAL` with clarification questions — never a fake high-confidence root cause or ready patch.
- A real issue description (what failed, where, after which action) is enough to search the repo. A log is helpful, not required.
- A patch is only labeled ready when verification status is `checks_passed`.
- First useful answer for typical interactive runs should complete within ~30–60s under normal local load (tracked via `metrics.total_duration_ms` / phase timings).
- Phase progress is streamed over SSE (`POST /investigation/run/stream`).
- Retrieval uses hybrid lexical + local embedding cosine similarity.
- Locate expands via import + AST/call-name graph hops.
- Patches are verified with syntax/lint and optional targeted tests / tsc.
- Live artifacts persist under `workspace/investigation_artifacts/{id}` with 30-day retention cleanup.
- Exact branch checkout is attempted when GitHub token + owner/repo are available and snapshot is missing.
- Golden suite runs in CI and nightly (`investigation-goldens-nightly.yml`).

## Evidence tiers
- **A**: vague description only → clarify
- **B**: a concrete description, or feature/action → locate + diagnosis; patch only if confidence high
- **C**: + console/network/backend log → full pipeline
- **D**: + live artifacts (request IDs, payloads, timing) → full pipeline with correlation leads

## Golden suite
See `backend/tests/fixtures/investigation_goldens.json` and `backend/tests/test_investigation_goldens.py`.
