# doc-warden-canary

Public KleinPerkins canary for Doc-Warden governance. Historical planning, ADR and
receipt records are retained as evidence; this CI transition does not resume the
held product work or grant new acceptance.

`make verify` runs three independent local lanes: engine-positive, engine-negative
and delivery-contracts. The engine lanes use the immutable public Dev revision in
`.github/ci-contract.json`; set `DOC_WARDEN_OWNER_SOURCE` to a checkout of that
revision. Tests use disposable fixture repositories and homes and assert that
read-only owner commands leave them unchanged. No home installation runs in CI.
GitHub Actions runs the same lanes separately; `ci-required` rejects missing,
failed, skipped, stale or incorrectly bound lane receipts.

PR creation rejects oversized review comments and validates the enabled producer,
origin, current adapters, runtime and exact allowed startup notices against the
reviewed enrollment policy before creating a PR or its origin witness.

Source delivery requires a fresh automatic independent review from the same Codex
account that creates the PR. Use `scripts/local_review.py` with the account's
qualified private enrollment, then `scripts/create_review_pr.py` to create the
ready PR and its creation-origin witness. Publish the unedited review receipt in
a PR comment prefixed with `<!-- g1-review-receipt:v1 -->`. A changed head, current
base or trusted policy requires a new review. Cloud is preferred when enrolled;
the accepted local adapter is an operational trust mechanism, not provider
attestation. WORK and PERSONAL credentials and enrollment remain distinct.

The trusted-main Reviewer App checks the creation witness, independent review,
exact hosted CI and effective controls before App-owned approval and native
squash. Initial automation admission is owner-only; source CI in a PR does not
establish trusted-main enrollment. Agents never merge manually, arm or cancel
auto-merge, bypass controls or restart the retired PR controller. Missing review
or admission holds delivery; the operator is not the technical reviewer.

The owner proves the complete allowed bypass-actor configuration during initial
admission. Runtime App credentials may redact that complete list; its visibility
remains unknown. Before approval and again before native delivery, the validated
App token must report `current_user_can_bypass: never` for every active ruleset
contributing to main. Unknown, incomplete or changed caller-specific evidence
rejects. This proves the App itself cannot bypass those rules at the read; it
does not reveal other hidden actors or eliminate later administrative races.
Code-owner review must be explicitly disabled in every applicable PR rule, while
the required App approval, stale dismissal and resolved-thread controls remain.

Local session-lock, identity-guard and data-guard remain required. Use LOCAL
`KleinPerkins <49759187+KleinPerkins@users.noreply.github.com>` identity. Repository
visibility, source merge, App activation and held Doc-Warden product acceptance
are separate outcomes.
