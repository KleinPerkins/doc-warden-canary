# Phase 01 — Canary end-to-end proof (zero-context native plan)

## Task 01-T01: Verify migrated v2 governance state

**Files:** `.planning/doc-warden.json` (read), `_ops/doc-warden/state/v2/receipts/` (read)

**Required reading:** ADR 0009 §§1-7; execution plan v2 §§3.6, 3.13.

**Interfaces:** consumes the migration receipt; produces a doctor verdict.

**Dependencies:** none (first task).

**Requirement IDs:** R1.

**Actions:** run `doc-warden doctor repo`; assert `profile=v2`, `write_enabled=true`.

**Tests:** `doctor repo` exit 0 with the expected JSON.

**Expected outcome:** the canary reports v2 active/write-enabled.

**Acceptance:** doctor JSON matches; receipt present for the migration operation.

**Rollback:** governed `git revert` of the migration commit.

**Evidence:** doctor JSON, migration receipt digest.

**Escalation:** dirty tree, receipt mismatch, or frozen-byte drift.
