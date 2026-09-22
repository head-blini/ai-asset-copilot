# Asset Copilot — Project Status

Last local verification: 2026-09-22 KST. Canonical repository: `head-blini/ai-asset-copilot`. Remote refs were queried with `git ls-remote` and fetched at R0 start. This document is part of an **unmerged R0 review branch**; the current merged `main` document state remains at the base SHA below until this PR merges.

## Ref and phase state

| Ref / scope | SHA and merge state | What it establishes |
| --- | --- | --- |
| `origin/main` | `0071d2b074be686392348ad6fbeec47d596e90de`, R0 base | Phase 0–3 code merged; Ledger, Market Data and current US analysis. No Policy API on main |
| `origin/feat/phase-4-policy-engine` | `089ee027bbdb03557d83cb081e0acd35694c23fe`, 4 commits ahead / 0 behind base, unmerged | Candidate Policy implementation; corrected code at `36eafe8e80d433fdf2f728b14a34be072ce67233`, later HEAD changes docs |
| `chore/project-rebaseline` | Review branch from `0071d2b` (head SHA recorded in PR) | R0 documentation and pytest CI only; no Policy implementation |

Phase 0–3: **DONE on main**. Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**. Phase 5–13 remain PLANNED; Phase 5 US Shadow Engine does not start while Phase 4 blockers remain. R0 review and any R0 merge are independent of Phase 4 completion. Candidate's earlier DONE statement was withdrawn because original Phase 4 criteria were not all met.

## Verification ledger

| Code actually tested | Environment and command | Result | Limit |
| --- | --- | --- | --- |
| main base `0071d2b074be686392348ad6fbeec47d596e90de` in clean R0 worktree before edits | Repository `.venv` Python 3.11.9, pytest 9.1.1; `/Users/DKLEE/Desktop/dk_project/ai-asset-copilot/.venv/bin/python -m pytest` | 133 collected, **133 passed**, 0 failed, 0 skipped, 0.76s | Main Phase 0–3 code only |
| candidate HEAD `089ee027bbdb03557d83cb081e0acd35694c23fe` in original candidate worktree | Same `.venv`; `.venv/bin/python -m pytest` | 219 collected, **219 passed**, 0 failed, 0 skipped, 0.98s | Candidate only; does not close P4-05/06/07/09 |
| R0 review worktree on base `0071d2b`, documentation/CI edits, `src/` and `tests/` unchanged; final commit SHA in PR | Same `.venv`; `/Users/DKLEE/Desktop/dk_project/ai-asset-copilot/.venv/bin/python -m pytest` | 133 collected, **133 passed**, 0 failed, 0 skipped, 0.84s | Local result before commit; rerun at committed head for final report |
| GitHub Actions PR #1 run [35697243360](https://github.com/head-blini/ai-asset-copilot/actions/runs/35697243360) on `a19bc9a1b30efb1b47c8affba157cb5648a7fccf` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed, 0 failed/skipped, pip check clean | Evidence for that exact head; later documentation/CI version update needs a fresh run |

No API key, real account, live Broker, or external Market Data call is required by these pytest runs. R0 worktree `.venv/bin/python -m pip check` found no broken requirements; `git diff --check` passed. Document links and phase rows are reviewed before commit. A local passing test is not a CI result.

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

R0 review PR [#1](https://github.com/head-blini/ai-asset-copilot/pull/1) is open against `main` and remains unmerged. Verify the CI run for its latest head after this evidence update, then review M1 ordering and input/report dependencies before adopting the proposed sequence adjustment.

After R0 review/merge, next feature work is a Phase 4 design review and implementation of P4-05/06/07: explicit ETF Core/Growth classification and complete allocation evaluation; immutable policy content/version/effective-time history; enforceable human approval and AI write denial. Preserve the candidate branch history, incorporate merged main through a normal merge, resolve documentation conflicts, rerun tests, and submit a separate Policy PR. Phase 4 remains blocked until P4-09 is met. Do not begin Phase 5 or enable live orders.
