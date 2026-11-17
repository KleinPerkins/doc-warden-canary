<!-- doc-warden:begin -->
## Documentation governance

This repo's documentation structure is governed by `doc-warden`.

| Artifact type | Location |
|---|---|
| Plans | `docs/plans/` — index at `docs/plans/README.md` |
| ADRs | `docs/adr/` — index at `docs/adr/README.md` |
| Runbooks | `docs/runbooks/` |
| Glossary | `docs/GLOSSARY.md` (created when genuine terminology ambiguity arises) |

**Policy:** `~/dev/_ops/doc-warden/POLICY.md`
**Engine:** `~/dev/_ops/bin/doc-warden.sh check doc-warden-canary` (read-only health check)
<!-- doc-warden:end -->

## G1 source delivery

Read README.md and the current `.github/review-enrollments.json` before source
changes. Preserve all held planning, ADR and historical receipt bytes. This
repository uses native GitHub Actions and the trusted-main Reviewer App; the
retired PR controller must not run.

Run `make verify` with the immutable owner source from `.github/ci-contract.json`.
Automatically obtain a fresh distinct-context review in the originating Codex
account using `scripts/local_review.py`; then create the ready PR through
`scripts/create_review_pr.py` and publish the unedited review receipt prefixed
with `<!-- g1-review-receipt:v1 -->`. Re-review after head, current base or trusted
policy changes. No qualified route means hold delivery, never human code review.

Only the admitted Reviewer App approves and arms native squash after exact CI
and review. Initial automation admission is owner-only. Agents never manually
merge, pre-arm/cancel auto-merge, bypass controls or infer App activation from
source publication. Verify the merged revision and effective gates before
reporting delivery. This transition does not resume held product work.
