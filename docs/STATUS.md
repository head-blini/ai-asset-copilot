# Asset Copilot — Project Status

Last local verification: 2026-09-25 (KST). Canonical repository: `head-blini/ai-asset-copilot`. This STATUS is on an unmerged Policy candidate, not on main. R0 PR #1 has its own unmerged documentation state.

## Current phase and Git evidence

- Phase 0–3: **DONE**, merged on main.
- Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**.
- Main / origin/main: `0071d2b074be686392348ad6fbeec47d596e90de`.
- Preserved Policy baseline: `feat/phase-4-policy-engine` at `089ee027bbdb03557d83cb081e0acd35694c23fe`.
- P4-05 review worktree: `feat/p4-allocation-completion`, based on that Policy SHA. R0 PR #1 remains separate at `9cd1a0f52b457352fca7d76500daac57d9dbdd25`.
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
| P4-05 | IN REVIEW / NOT DONE | Separate candidate adds explicit asset_id Core/Growth classification, four retained Target/Range bands, reconciled USD allocation decisions and offline SQLite/Analytics example; code review and PR CI remain separate gates |
| P4-06 | OPEN | policy_version is only a string; change history, approval/effective-time linkage and historical configuration retention are absent |
| P4-07 | OPEN | Frozen config and comments do not enforce human approval or deny unauthorized policy writes |
| P4-08 | PASS | Full regressions preserve deterministic Decimal comparisons and sums, immutable input/output, stale/invalid evidence → UNKNOWN, and no evaluator Repository/Provider/clock calls |
| P4-09 | OPEN | P4-05 review plus P4-06/07 and full review/main merge still block Phase completion. No next Phase implementation |

## Governance reconciliation

Uncommitted local AGENTS/ROADMAP/STATUS were inspected and backed up before editing. Useful rules about deterministic replay, provider boundaries, preserving work, project-environment tests, documentation updates and completion gates are retained. Local Phase numbering, the Phase 5 performance plan, and unverified broker selection were not adopted. The obsolete statement that repository access is unavailable was removed: Git remote access works in this workspace.

The candidate's ROADMAP and PROJECT_SPEC completion claims are retracted. The original main Phase 0–13 sequence and Phase 4 history/permissions/range requirements remain the basis for review. No requirement has been moved to a later Phase to permit DONE.

## Immediate next work and limits

Review the isolated P4-05 candidate without merging R0 or the Policy branch into main. The next implementation task after this candidate review is a small design review and P4-06/07 implementation of policy content/version/effective-time history, human approval, and AI write denial. These are existing Phase 4 blockers, not requirements transferred to a future Phase. The wider first-user path and follow-up order are in ROADMAP; Toss read capability research is independent and grants no account or order access.

No ETF look-through, Policy write authorization, overall compliance verdict, rebalancing, or order approval is claimed by the candidate evaluator. A bucket PASS does not override an independent Risk BREACH or establish Phase completion. Phase 5 implementation is prohibited while these blockers remain.

## Correctness decisions and remaining limitations

- `individual_position_max` and `concentration_warning` mean individual STOCK limits, consistent with the Individual Stocks bucket and separate Core/Growth ETF allocation targets. The candidate API was renamed accordingly; the unmerged SINGLE_ASSET API is not retained as an ambiguous alias.
- Total STOCK exposure includes all direct STOCK positions even when sector is unknown. ETF positions and cash are excluded from its numerator; cash remains in the denominator. Concentration equality (including the 30% total cap) is BREACH. The future allocation range cannot override a risk breach.
- Core/Growth membership is explicit per ETF `asset_id` input, never inferred from ticker. Missing ETF classification yields `UNKNOWN` for ETF allocation buckets. Each target/range is retained and evaluated against exact USD amounts with inclusive range edges; a target difference alone does not warn or order. Malformed or unreconciled analysis yields `UNKNOWN`, and allocation and Risk results remain separate.
- Config version is an opaque label, not a schema version or authorization token. Unknown keys fail closed, but genuine human authorization/history requires the still-open P4-06/P4-07 design and tests.
- Empty zero-value analysis returns UNKNOWN for cash and total STOCK ratios. Cash-only/ETF-only positive portfolios have zero total STOCK exposure; absent individual STOCK/direct-sector targets are not_applicable.
- The original `681ef60` and its corrected descendants remain candidates. Main merge is **not performed** because scope/authorization/history blockers remain. Phase 5 entry is **not permitted**.
