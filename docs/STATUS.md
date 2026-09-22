# Asset Copilot — Project Status

Last verified: 2026-09-22 (KST). Canonical repository: `head-blini/ai-asset-copilot`.

## Current phase and Git evidence

- Phase 0–3: **DONE**, merged on main.
- Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**.
- Main / origin/main: `0071d2b074be686392348ad6fbeec47d596e90de`.
- Candidate branch: `feat/phase-4-policy-engine`.
- Original candidate implementation: `681ef60e3977eda701c7544cfcd32d9b5e685071` (not merged).
- Corrected candidate: the source/test correction commit accompanying this status; an exact SHA provenance update follows without further source changes.
- Governance recovery commit: `c810c56a23cc9081fafac702e8a545107bb89f17`.
- Remote refs checked directly on GitHub via `git ls-remote`; candidate was 1 commit ahead / 0 behind main at audit start.
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

- Environment: repository `.venv`, Python 3.11.9, pytest 9.1.1.
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
| P4-05 | OPEN | Core/Growth classification is absent; allocation Target/Range evaluation is not implemented |
| P4-06 | OPEN | policy_version is only a string; change history, approval/effective-time linkage and historical configuration retention are absent |
| P4-07 | OPEN | Frozen config and comments do not enforce human approval or deny unauthorized policy writes |
| P4-08 | PASS | Full regressions preserve deterministic Decimal comparisons and sums, immutable input/output, stale/invalid evidence → UNKNOWN, and no evaluator Repository/Provider/clock calls |
| P4-09 | OPEN | Correctness fixes and all tests pass; P4-05/06/07 block Phase completion and main merge. No next Phase implementation |

## Governance reconciliation

Uncommitted local AGENTS/ROADMAP/STATUS were inspected and backed up before editing. Useful rules about deterministic replay, provider boundaries, preserving work, project-environment tests, documentation updates and completion gates are retained. Local Phase numbering, the Phase 5 performance plan, and unverified broker selection were not adopted. The obsolete statement that repository access is unavailable was removed: Git remote access works in this workspace.

The candidate's ROADMAP and PROJECT_SPEC completion claims are retracted. The original main Phase 0–13 sequence and Phase 4 history/permissions/range requirements remain the basis for review. No requirement has been moved to a later Phase to permit DONE.

## Immediate next work and limits

Next task is a Phase 4 design review of (1) explicit Core/Growth ETF classification and full allocation Target/Range evaluation, and (2) the human policy approval, change history, immutable version content and effective-time contract. Implement and test those accepted contracts before reconsidering P4-05/06/07. These are existing Phase 4 blockers, not requirements transferred to a future Phase. No ticker inference or new financial defaults were introduced in this audit.

No ETF look-through, Policy write authorization, full allocation compliance, rebalancing, or order approval is claimed by the current evaluator. An individual PASS is not a full-portfolio or Phase-completion verdict. Phase 5 implementation is prohibited while these blockers remain.

## Correctness decisions and remaining limitations

- `individual_position_max` and `concentration_warning` mean individual STOCK limits, consistent with the Individual Stocks bucket and separate Core/Growth ETF allocation targets. The candidate API was renamed accordingly; the unmerged SINGLE_ASSET API is not retained as an ambiguous alias.
- Total STOCK exposure includes all direct STOCK positions even when sector is unknown. ETF positions and cash are excluded from its numerator; cash remains in the denominator. Concentration equality (including the 30% total cap) is BREACH. The future allocation range cannot override a risk breach.
- Core/Growth ETF membership does not exist in Domain; no classification is inferred. Valid target/range declarations are schema-validated but are not yet fully evaluated. An ETF without an individual STOCK evaluation is not a full-policy PASS.
- Config version is an opaque label, not a schema version or authorization token. Unknown keys fail closed, but genuine human authorization/history requires the still-open P4-06/P4-07 design and tests.
- Empty zero-value analysis returns UNKNOWN for cash and total STOCK ratios. Cash-only/ETF-only positive portfolios have zero total STOCK exposure; absent individual STOCK/direct-sector targets are not_applicable.
- The original `681ef60` and its corrected descendants remain candidates. Main merge is **not performed** because scope/authorization/history blockers remain. Phase 5 entry is **not permitted**.
