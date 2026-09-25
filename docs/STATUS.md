# Asset Copilot — Project Status

Last local verification: 2026-09-25 KST. Canonical repository: `head-blini/ai-asset-copilot`. Remote refs were queried with `git ls-remote` on 2026-09-25. This document is part of an **unmerged R0 review branch**; the current merged `main` document state remains at the base SHA below until this PR merges.

## Ref and phase state

| Ref / scope | SHA and merge state | What it establishes |
| --- | --- | --- |
| `origin/main` | `0071d2b074be686392348ad6fbeec47d596e90de`, R0 base | Phase 0–3 code merged; Ledger, Market Data and current US analysis. No Policy API on main |
| `origin/feat/phase-4-policy-engine` | `089ee027bbdb03557d83cb081e0acd35694c23fe`, 4 commits ahead / 0 behind base, unmerged | Candidate Policy implementation; corrected code at `36eafe8e80d433fdf2f728b14a34be072ce67233`, later HEAD changes docs |
| `chore/project-rebaseline` | PR #1 reviewed head `c37ca413d600adf1b178c50d6109123771209900`, from `0071d2b`; subsequent head is recorded in the PR | R0 documentation and pytest CI only; no Policy implementation |

Phase 0–3: **DONE on main**. Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**. Phase 5–13 remain PLANNED; Phase 5 US Shadow Engine does not start while Phase 4 blockers remain. R0 review and any R0 merge are independent of Phase 4 completion. Candidate's earlier DONE statement was withdrawn because original Phase 4 criteria were not all met.

## Verification ledger

| Code actually tested | Environment and command | Result | Limit |
| --- | --- | --- | --- |
| PR #1 reviewed head `c37ca413d600adf1b178c50d6109123771209900` | macOS, repository `.venv` Python 3.11.15, pytest 9.1.1; `.venv/bin/python -m pytest`, `.venv/bin/python -m pip check`, `git diff --check` (2026-09-25) | **133 passed**, 0 failed/skipped, 0.31s; no broken requirements; diff check passed | Local result for this exact head |
| GitHub Actions PR #1 [run 35697851552](https://github.com/head-blini/ai-asset-copilot/actions/runs/35697851552) on `c37ca413d600adf1b178c50d6109123771209900` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed, 0 failed/skipped; no broken requirements | CI result for this exact head; run logs checked |
| main base `0071d2b074be686392348ad6fbeec47d596e90de` in clean R0 worktree before edits | Repository `.venv` Python 3.11.9, pytest 9.1.1; `.venv/bin/python -m pytest` | 133 collected, **133 passed**, 0 failed, 0 skipped, 0.76s | Main Phase 0–3 code only |
| candidate HEAD `089ee027bbdb03557d83cb081e0acd35694c23fe` in original candidate worktree | Same `.venv`; `.venv/bin/python -m pytest` | 219 collected, **219 passed**, 0 failed, 0 skipped, 0.98s | Candidate only; does not close P4-05/06/07/09 |
| Earlier GitHub Actions PR #1 [run 35697243360](https://github.com/head-blini/ai-asset-copilot/actions/runs/35697243360) on `a19bc9a1b30efb1b47c8affba157cb5648a7fccf` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed, 0 failed/skipped, pip check clean | Historical evidence for the earlier head |

No API key, real account, live Broker, or external Market Data call is required by these pytest runs. Local tests and GitHub Actions are separate results tied to their exact SHA.

## Candidate Phase 4 acceptance review

The [ROADMAP P4 gate](ROADMAP.md#phase-4-canonical-acceptance-criteria) retains the original main acceptance scope. The candidate review at `089ee02` records P4-01/02/03/04/08 as passing its local tests. **P4-05 OPEN:** Core/Growth classification and full Target/Range evaluation. **P4-06 OPEN:** immutable Policy content, change history, version/effective-time linkage and historical replay. **P4-07 OPEN:** enforceable human approval and AI write/Risk bypass denial. **P4-09 OPEN:** all conditions, review, main merge and status update. No individual PASS means full-portfolio compliance, and candidate code remains unmerged.

## User path and current limits

| Existing function | Actual file / state | User reach |
| --- | --- | --- |
| Ledger replay and SQLite append | `src/asset_copilot/domain/models.py`, `storage/sqlite.py`; merged main | Python API; no real account import, correction or reconciliation interface |
| Price/FX normalization | `src/asset_copilot/market/twelve_data.py`; merged main | Adapter with provenance; rights, freshness policy and operational feed unresolved |
| Current US account analysis | `src/asset_copilot/application/us_portfolio_analytics.py`; merged main | Python API; no user report/delivery path |
| Human Policy candidate | `src/asset_copilot/application/{policy_config,us_portfolio_policy}.py`; candidate only | Partial evaluation; not in main, not full M1 report |
| Shadow, AI, Korean paper/live, dashboard, operations | ROADMAP Phase 5–13; planned | Not a current runtime user flow |

The M1 input → validation/reconciliation → Ledger → observed prices/FX → analytics → approved Policy → provenance-aware minimal report path is a **plan**, not a current product capability. M1 report ordering is pending review; Phase 11's full Dashboard/Daily/Weekly scope remains. Account input method, Broker capability (including Toss), trading cadence, market data rights and live capital operation limits remain open decisions in PROJECT_SPEC. No real account fixture is committed.

## R0 next work and blockers

R0 review PR [#1](https://github.com/head-blini/ai-asset-copilot/pull/1) is open against `main` and remains unmerged. Its reviewed head `c37ca41` has a successful CI run. Review M1 ordering and input/report dependencies before adopting the proposed sequence adjustment.

After R0 review/merge, next feature work is a Phase 4 design review and implementation of P4-05/06/07: explicit ETF Core/Growth classification and complete allocation evaluation; immutable policy content/version/effective-time history; enforceable human approval and AI write denial. Preserve the candidate branch history, incorporate merged main through a normal merge, resolve documentation conflicts, rerun tests, and submit a separate Policy PR. Phase 4 remains blocked until P4-09 is met. Do not begin Phase 5 or enable live orders.
