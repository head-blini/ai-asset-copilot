# Asset Copilot — Project Status

Last local verification: 2026-09-27 (KST). Canonical repository: `head-blini/ai-asset-copilot`. This STATUS is on an unmerged Policy candidate, not on main. Its older R0/main descriptions below are historical; current main STATUS controls adopted feature state. Remote main `77a832b5d718ab78a2ce4ded8e1df219c1e6883d` has BUD-01 and WEB-01 complete for their offline and local-preview gates, respectively. Their code and status are unchanged by this candidate.

## Current phase and Git evidence

- Phase 0–3: **DONE**, merged on main.
- Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**.
- P4-06/07 follow-up branch: `feat/p4-policy-history-approval`, forked from reviewed P4-05 head `e49be74d1e07ea67f8a629f9f0d149fddb82d858`; code/test commit `3ad5b0c280e30aaad29d4f18503a25197c53c1f9`. This candidate depends on PR #2, whose head/base remain unchanged. It is not in main.
- Current origin/main: `77a832b5d718ab78a2ce4ded8e1df219c1e6883d`; `0071d2b074be686392348ad6fbeec47d596e90de` below is the historical Policy-branch fork baseline, not current main.
- Preserved Policy baseline: `feat/phase-4-policy-engine` at `089ee027bbdb03557d83cb081e0acd35694c23fe`.
- P4-05 review worktree: `feat/p4-allocation-completion`, based on that Policy SHA. R0 PR #1 was subsequently merged into main; this Policy branch has not merged current main.
- Original candidate implementation: `681ef60e3977eda701c7544cfcd32d9b5e685071` (not merged).
- Audited corrected Policy implementation SHA: `36eafe8e80d433fdf2f728b14a34be072ce67233`.
- Subsequent verification-record commits change documentation only; the remote branch HEAD identifies the latest governance document revision.
- Governance recovery commit: `c810c56a23cc9081fafac702e8a545107bb89f17`.
- Remote refs checked directly via `git ls-remote` on 2026-09-25: main `0071d2b074be686392348ad6fbeec47d596e90de`, R0 `9cd1a0f52b457352fca7d76500daac57d9dbdd25`, Policy `089ee027bbdb03557d83cb081e0acd35694c23fe`. The original candidate was 1 commit ahead / 0 behind main at audit start.
- Phase 4 merge: **NO**. Next-phase entry: **NO**. Phase 5 remains US Shadow Engine and is not started.
- Governance corrections on this review branch are published as review-state evidence, not a claim that main contains the Policy Engine. Main adoption remains subject to the merge gate.

## Phase board

| Phase | Canonical name | State |
| --- | --- | --- |
| 0 | Project Bootstrap / Architecture | DONE |
| 1 | Portfolio Foundation | DONE |
| 2 | Market Data | DONE |
| 3 | US Portfolio Analytics | DONE |
| 4 | US Portfolio Policy | IN REVIEW / NOT DONE |
| 5 | US Shadow Engine | PLANNED; entry prohibited until Phase 4 closes |
| 6 | Research / Investment Thesis | PLANNED |
| 7 | AI Asset Copilot | PLANNED |
| 8 | KR Paper Trading | PLANNED |
| 9 | KR Strategy / Backtest | PLANNED |
| 10 | KR Live-market Paper Trading | PLANNED |
| 11 | Dashboard / Daily / Weekly Report | PLANNED |
| 12 | Broker Integration | PLANNED |
| 13 | Limited KR Live Trading | PLANNED |

## Verification and audit evidence

- P4-06/07 code/test SHA `3ad5b0c280e30aaad29d4f18503a25197c53c1f9`: baseline at clean `e49be74` in the existing P4 worktree's `.venv` (macOS Python 3.11.15, editable evaluator import from this worktree) ran `.venv/bin/python -m pytest -q` → **271 passed**, `.venv/bin/python -m pip check` → clean, `git diff --check` → clean, and `.venv/bin/python examples/p4_allocation_offline.py` → expected complete PASS and missing-classification UNKNOWN. After the code/test change, the same commands gave **277 passed**, clean pip/diff, and the original example retained its output; `.venv/bin/python examples/p4_policy_history_offline.py` demonstrated unapproved selection failure, approval-target tamper rejection, subsequent pending revision not replacing the applied one, and identical replay after reopening SQLite. These are local results; candidate-head CI and review are separate gates.
- P4-05 PR #2 evidence refreshed on 2026-09-27: head `e49be74d1e07ea67f8a629f9f0d149fddb82d858`, base `089ee027bbdb03557d83cb081e0acd35694c23fe`; GitHub Actions run `36248104411` succeeded on generated merge checkout `656c0481accfd281dd262006e2f6296aac38724a`, Ubuntu Python 3.11.16 / pytest 9.1.1, **271 passed**, pip check clean. The PR body was corrected; its head and base were not changed. This does not establish P4-06/07 CI.
- P4-06 implementation candidate: one-read TOML bytes, validated immutable config and raw-source hash bound into a unique content ID; append-only SQLite revision chain with scope/version uniqueness, expected-head compare-and-set, idempotent request IDs, conflict rejection and atomic transactions. Recorded evaluations retain the exact analysis, ETF classification tuple, result, revision/content ID, times and evaluator implementation fingerprint; replay uses the stored inputs and rejects mismatches. No Ledger or Budget table changes.
- P4-07 implementation candidate: a trusted local operator path receives a secret approval key and the policy-write repository. The approval proof signs revision/content/scope/approval/effective times; applying verifies it and disallows backdating. The evaluator path has no policy-write API and its SQLite authorizer denies policy table writes; `PolicyReader` opens read-only SQLite. Tests cover forged/reused/tampered evidence, stale proposals, simultaneous connection conflict, failed insert rollback, selection boundaries and read-only write denial. This does **not** establish protection against arbitrary Python running under the same OS identity with access to the key or database; deployment key custody, OS user/file separation and human identity verification remain untested blockers to P4-07 DONE.
- P4-05 malformed STOCK `asset_id` follow-up: starting PR #2 head `d1beb1b8e0cfc25371ed2dc6954cd85bf18e12f0` in this clean worktree's `.venv` (macOS Python 3.11.15, pytest 9.1.1; evaluator import resolved to this checkout) reran `.venv/bin/python -m pytest` → **265 passed**, `.venv/bin/python -m pip check` → clean, `git diff --check` → clean, and `.venv/bin/python examples/p4_allocation_offline.py` → four complete PASS buckets and expected Core/Growth UNKNOWN without one classification. Independent full `evaluate()` reproduction split a reconciled 25 USD STOCK holding into two 12.5 USD positions: normal string IDs passed in both orders; `None`, integer and list IDs raised `TypeError` from `sorted()` in both orders; empty and whitespace IDs returned UNKNOWN. The new targeted regression then produced **3 failed, 3 passed, 132 deselected** before the fix. Code/test commit `416ee923d8a2e845e27a4f0ebe337d4e52df9244` sorts only after position shape validation and reports malformed individual-stock identity as UNKNOWN without a partial PASS. On that code SHA, `.venv/bin/python -m pytest` → **271 passed** (policy file: 138 passed), `.venv/bin/python -m pip check` → clean, `git diff --check` → clean, and the offline example retained its output. Invalid position Risk reasons remain `UNRELIABLE_ANALYSIS`; all four allocation reasons remain `INVALID_ANALYSIS`. Valid unclassified ETF and incomplete direct-sector evidence retain their separate handling; explicitly invalid ETF classification input is still rejected. New-head CI must be checked after push and is not established by these local results.
- P4-05 review correction, code/test SHA `938fec30cecc8e35bfcc432d0d2715e0f6097aea`: baseline PR #2 head `709e12f1bb82ea65bf94d83c890d24ebcd585f96` rerun in this worktree with `.venv/bin/python -m pytest` → **261 passed**. Four new targeted cases then failed before the fix: malformed extra position incorrectly produced allocation PASS twice; malformed direct-sector members raised `AttributeError` twice. After the correction at the code/test SHA, `.venv/bin/python -m pytest` → **265 passed in 0.31s**, `.venv/bin/python -m pip check` → no broken requirements, `git diff --check` → pass. `.venv/bin/python examples/p4_allocation_offline.py` still reports four complete PASS allocations and ETF Core/Growth UNKNOWN when a classification is missing. macOS Python 3.11.15, pytest 9.1.1; `asset_copilot.__file__` resolves to this worktree. This is local evidence; updated PR head CI must be checked separately.
- The correction checks original `analysis.positions` before allocation rather than accepting filtered valid positions. Direct-sector members are validated before sorting; invalid structure yields an explicit direct-sector UNKNOWN while independent total-STOCK and cash results remain available. Existing normal classification, concentration, inclusive cash/range and Decimal behavior is unchanged.
- P4-05 worktree environment: its own `.venv`, macOS, Python 3.11.15, pytest 9.1.1; `asset_copilot.__file__` resolves to this checkout's `src/asset_copilot`. This is a local environment, not GitHub Actions.
- Exact pre-change baseline `089ee027bbdb03557d83cb081e0acd35694c23fe`: `.venv/bin/python -m pytest` → **219 passed in 0.38s**, 0 failed/skipped, rerun on 2026-09-25 before P4-05 edits.
- P4-05 code commit `bece80a03255e50c8d9149c818495cbe5f148104`, based on `089ee02`: its source/test tree was checked in the review worktree before commit with `.venv/bin/python -m pytest` → **261 passed in 0.32s**, 0 failed/skipped; `.venv/bin/python -m pip check` → no broken requirements; `git diff --check` → pass. `.venv/bin/python examples/p4_allocation_offline.py` produced four classified range decisions and `UNKNOWN` for both ETF buckets when one classification was omitted. Final PR head CI is a separate check.
- Historical audit environment: repository `.venv`, Python 3.11.9, pytest 9.1.1 (2026-09-22).
- Baseline `681ef60`: `.venv/bin/python -m pytest` → **178 passed** (133 Phase 0–3 regression tests + 45 policy tests), rerun before corrections.
- Corrected candidate: `.venv/bin/python -m pytest` → **219 passed in 0.89s** (133 Phase 0–3 regression tests + 86 policy tests). No skipped or failed tests.
- The original Phase 0–3 source/contracts and regression assertions are unchanged. Prior ETF assertions were corrected to the audited STOCK-only contract; stock equality, sector, cash, immutability and reliability assertions are retained.
- Added 41 cases for strict schema, malformed values, total STOCK boundaries/precision/UNKNOWN, and ETF exclusion.
- `git diff --check`: PASS. All 14 Phase rows match main `0071d2b`; parsed TOML policy values also match that commit exactly.
- `.venv/bin/python -m pip check`: **No broken requirements found**. Sandbox pip-cache warning does not affect the check.
- No lint/type-check command is configured in pyproject.toml.
- Green tests establish the corrected evaluator behavior, not completion of the unimplemented acceptance criteria below.

## Phase 4 acceptance review

Criteria are defined in ROADMAP; they have not been reduced to fit the candidate.

| ID | State | Evidence / remaining work |
| --- | --- | --- |
| P4-01 | PASS | Loader validates every table/key, required fields, Decimal percentages, sums and ranges; unknown/missing keys, malformed types, NaN/Infinity and duplicate TOML keys are rejected |
| P4-02 | PASS | INDIVIDUAL_STOCK and individual_stock_* config fields apply only to AssetType.STOCK. A 50% ETF does not receive the individual-stock cap; existing policy values are unchanged |
| P4-03 | PASS | TOTAL_STOCK_EXPOSURE uses the configured 30% cap, exact sum of STOCK amounts including unclassified stocks, cash-inclusive total denominator, and stock_exposure availability. Below/equal/above, precision and invalid evidence tests pass |
| P4-04 | PASS | Direct STOCK sector, unclassified UNKNOWN, cash range and cash-inclusive denominator tests pass |
| P4-05 | IN REVIEW / NOT DONE | Separate candidate adds explicit asset_id Core/Growth classification, four retained Target/Range bands, reconciled USD allocation decisions and offline SQLite/Analytics example; its latest head CI passed, but review/main adoption remain separate gates |
| P4-06 | IMPLEMENTED / LOCALLY VERIFIED / IN REVIEW | Separate follow-up candidate adds source-linked immutable revisions, applied-time selection and stored-input evaluation replay; PR review and CI remain open |
| P4-07 | PARTIAL / LOCALLY VERIFIED / IN REVIEW | Signed, scoped approval and read-only/evaluator write denial are tested locally; real operator identity, key custody and OS process/file permissions are not verified, so authority gate is not complete |
| P4-08 | PASS | Full regressions preserve deterministic Decimal comparisons and sums, immutable input/output, stale/invalid evidence → UNKNOWN, and no evaluator Repository/Provider/clock calls |
| P4-09 | IN REVIEW / NOT DONE | P4-05 and P4-06/07 review, authority-boundary verification and full main integration/merge still block Phase completion. No next Phase implementation |

## Governance reconciliation

Uncommitted local AGENTS/ROADMAP/STATUS were inspected and backed up before editing. Useful rules about deterministic replay, provider boundaries, preserving work, project-environment tests, documentation updates and completion gates are retained. Local Phase numbering, the Phase 5 performance plan, and unverified broker selection were not adopted. The obsolete statement that repository access is unavailable was removed: Git remote access works in this workspace.

The candidate's ROADMAP and PROJECT_SPEC completion claims are retracted. The original main Phase 0–13 sequence and Phase 4 history/permissions/range requirements remain the basis for review. No requirement has been moved to a later Phase to permit DONE.

## Immediate next work and limits

Review PR #2 and the dependent P4-06/07 candidate separately. Verify the operator identity/key custody and OS isolation boundary before P4-07 completion; then reconcile this candidate against latest main while preserving BUD-01/WEB-01 code, optional web dependencies, Core/web CI and their actual DONE status. Do not merge current main into PR #2 merely to perform that later integration. P4-09 needs complete review and main merge before Phase 4 can close. The wider first-user path and follow-up order are in ROADMAP; Toss read capability research is independent and grants no account or order access.

No ETF look-through, Policy write authorization, overall compliance verdict, rebalancing, or order approval is claimed by the candidate evaluator. A bucket PASS does not override an independent Risk BREACH or establish Phase completion. Phase 5 implementation is prohibited while these blockers remain.

## Correctness decisions and remaining limitations

- `individual_position_max` and `concentration_warning` mean individual STOCK limits, consistent with the Individual Stocks bucket and separate Core/Growth ETF allocation targets. The candidate API was renamed accordingly; the unmerged SINGLE_ASSET API is not retained as an ambiguous alias.
- Total STOCK exposure includes all direct STOCK positions even when sector is unknown. ETF positions and cash are excluded from its numerator; cash remains in the denominator. Concentration equality (including the 30% total cap) is BREACH. The future allocation range cannot override a risk breach.
- Core/Growth membership is explicit per ETF `asset_id` input, never inferred from ticker. Missing ETF classification yields `UNKNOWN` for ETF allocation buckets. Each target/range is retained and evaluated against exact USD amounts with inclusive range edges; a target difference alone does not warn or order. Malformed or unreconciled analysis yields `UNKNOWN`, and allocation and Risk results remain separate.
- Config version is an opaque label, not a schema version or authorization token. The follow-up candidate binds source and validated content into a revision and adds a signed operator path, but actual human identity/key and OS isolation verification remains open.
- Empty zero-value analysis returns UNKNOWN for cash and total STOCK ratios. Cash-only/ETF-only positive portfolios have zero total STOCK exposure; absent individual STOCK/direct-sector targets are not_applicable.
- The original `681ef60` and its corrected descendants remain candidates. Main merge is **not performed** because scope/authorization/history blockers remain. Phase 5 entry is **not permitted**.
