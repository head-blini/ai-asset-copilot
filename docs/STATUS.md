# Asset Copilot — Project Status

Last verified: 2026-09-22 (KST). Canonical repository: `head-blini/ai-asset-copilot`.

## Current phase and Git evidence

- Phase 0–3: **DONE**, merged on main.
- Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**.
- Main / origin/main: `0071d2b074be686392348ad6fbeec47d596e90de`.
- Candidate branch: `feat/phase-4-policy-engine`.
- Candidate implementation under audit: `681ef60e3977eda701c7544cfcd32d9b5e685071`.
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

## Verification of 681ef60 candidate

- Environment: repository `.venv`, Python 3.11.9, pytest 9.1.1.
- `.venv/bin/python -m pytest`: **178 passed** (133 Phase 0–3 regression tests + 45 policy tests), rerun during this audit.
- `.venv/bin/python -m pip check`: **No broken requirements found**. Sandbox pip-cache warning does not affect the check.
- No lint/type-check command is configured in pyproject.toml.
- Green tests do not establish Phase 4 completion: the old suite asserted the incorrect ETF single-asset limit and did not exercise the missing total STOCK policy.

## Phase 4 acceptance review

Criteria are defined in ROADMAP; they have not been reduced to fit the candidate.

| ID | State | Evidence / remaining work |
| --- | --- | --- |
| P4-01 | OPEN | Loader exists but ignores unknown keys; strict schema tests/fix required |
| P4-02 | OPEN | SINGLE_ASSET applies the individual-stock 15% cap to ETF as well; scope/name/test correction required |
| P4-03 | OPEN | 30% total STOCK limit is read and discarded; real evaluation and boundary tests required |
| P4-04 | PASS | Direct STOCK sector, unclassified UNKNOWN, cash range and cash-inclusive denominator tests pass |
| P4-05 | OPEN | Core/Growth classification is absent; allocation Target/Range evaluation is not implemented |
| P4-06 | OPEN | policy_version is only a string; change history, approval/effective-time linkage and historical configuration retention are absent |
| P4-07 | OPEN | Frozen config and comments do not enforce human approval or deny unauthorized policy writes |
| P4-08 | PASS | Existing deterministic Decimal evaluator, immutable records and freshness failure tests pass; preserve during corrections |
| P4-09 | OPEN | Review found correctness and scope blockers; candidate is not merged |

## Governance reconciliation

Uncommitted local AGENTS/ROADMAP/STATUS were inspected and backed up before editing. Useful rules about deterministic replay, provider boundaries, preserving work, project-environment tests, documentation updates and completion gates are retained. Local Phase numbering, the Phase 5 performance plan, and unverified broker selection were not adopted. The obsolete statement that repository access is unavailable was removed: Git remote access works in this workspace.

The candidate's ROADMAP and PROJECT_SPEC completion claims are retracted. The original main Phase 0–13 sequence and Phase 4 history/permissions/range requirements remain the basis for review. No requirement has been moved to a later Phase to permit DONE.

## Immediate next work and limits

Correct the individual STOCK scope, enforce total STOCK exposure, and reject malformed/unknown policy schema. Then rerun the full suite and update this acceptance table. Core/Growth classification, complete allocation evaluation, and human policy history/approval/effective-time contracts remain explicit Phase 4 blockers; do not invent these decisions merely to obtain a green completion gate.

No ETF look-through, Policy write authorization, full allocation compliance, rebalancing, or order approval is claimed by the current evaluator. An individual PASS is not a full-portfolio or Phase-completion verdict. Phase 5 implementation is prohibited while these blockers remain.
