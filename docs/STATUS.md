# Asset Copilot — Project Status

Last local verification: 2026-09-25 KST. Canonical repository: `head-blini/ai-asset-copilot`. Remote refs were queried with `git ls-remote` on 2026-09-25. This **unmerged BUD-01 code candidate** is based on PR #3's documentation branch, which depends on unmerged R0 PR #1. The current merged `main` document/code state remains at the base SHA below. Budget/Cashflow is a new product scope; only its BUD-01 offline calculator is a candidate, not a deployed feature.

## Ref and phase state

| Ref / scope | SHA and merge state | What it establishes |
| --- | --- | --- |
| `origin/main` | `0071d2b074be686392348ad6fbeec47d596e90de`, R0 base | Phase 0–3 code merged; Ledger, Market Data and current US analysis. No Policy API on main |
| `origin/feat/phase-4-policy-engine` | `089ee027bbdb03557d83cb081e0acd35694c23fe`, 4 commits ahead / 0 behind base, unmerged | Candidate Policy implementation; corrected code at `36eafe8e80d433fdf2f728b14a34be072ce67233`, later HEAD changes docs |
| `chore/project-rebaseline` | PR #1 head `9cd1a0f52b457352fca7d76500daac57d9dbdd25`, from `0071d2b`; open/unmerged | R0 documentation and pytest CI only; no Policy implementation. This Budget document branch starts here |
| `feat/p4-allocation-completion` | PR #2 head `d1beb1b8e0cfc25371ed2dc6954cd85bf18e12f0`, based on `089ee02`; open/unmerged | P4-05 review correction and CI candidate, separate from R0 and this Budget document branch |
| `docs/budget-cashflow-scope` | PR #3 head `d58a4d32d217998697ff7e3706ded1e8e91631c8`, based on R0; open/unmerged | Budget scope and subsequent home/retirement/access decisions; this BUD-01 candidate starts at exactly this SHA |
| `feat/budget-monthly-foundation` | local latest code/test commit `27937b27c9d332420768f8920b7370df8f1c618a`, based on PR #3 head; PR/head CI recorded separately | BUD-01 pure calculator and three offline examples only; no BUD-02/03 implementation |

Phase 0–3: **DONE on main**. Phase 4 — **US Portfolio Policy: IN REVIEW / NOT DONE**. P4-05 has a separate review candidate but is not merged or accepted; P4-06/07/09 remain open. Phase 5–13 remain PLANNED; Phase 5 US Shadow Engine does not start while Phase 4 blockers remain. R0 review and any R0 merge are independent of Phase 4 completion. Candidate's earlier DONE statement was withdrawn because original Phase 4 criteria were not all met.

## Verification ledger

| Code actually tested | Environment and command | Result | Limit |
| --- | --- | --- | --- |
| BUD-01 baseline `d58a4d32d217998697ff7e3706ded1e8e91631c8` before code edits | New worktree `.venv`, macOS Python 3.11.15, pytest 9.1.1, editable import from this checkout; `.venv/bin/python -m pytest`, `.venv/bin/python -m pip check` | **133 passed in 0.31s**, no broken requirements | PR #3 documentation base only; no Budget engine at this SHA |
| BUD-01 latest code/test commit `27937b27c9d332420768f8920b7370df8f1c618a` | macOS, this worktree `.venv` Python 3.11.15, pytest 9.1.1, editable import from `src/asset_copilot/budget`; `.venv/bin/python -m pytest`, `.venv/bin/python -m pip check`, `.venv/bin/python examples/budget_monthly_offline.py --scenario all` | **155 passed in 0.27s**, no broken requirements; normal monthly margin 730 with two funded goal dates, Sep 10 end-of-day cash shortage 400 despite positive month end, unknown home target/deadline has `None` contribution and known cashflow | Local exact code/test SHA; this documentation commit and PR CI need separate verification |
| BUD-01 code/test commit `8dd0ddde386c12646cc0595f12ba2fec86134cb0` | macOS, this worktree's `.venv` Python 3.11.15, pytest 9.1.1, editable import from this worktree; `.venv/bin/python -m pytest`, `.venv/bin/python -m pip check`, `.venv/bin/python examples/budget_monthly_offline.py --scenario all` | **154 passed in 0.27s** (133 baseline + 21 BUD-01); no broken requirements; normal margin 730, cash-gap day 10 shortage 400 despite month-end +600, unknown home goal required amount `None` with known cashflow | Local result for code/test SHA, before this documentation/report-format revision; final PR head and CI must be checked separately |
| PR #3 current head `d58a4d32d217998697ff7e3706ded1e8e91631c8`, Actions [run 36121340596](https://github.com/head-blini/ai-asset-copilot/actions/runs/36121340596), PR merge checkout `2769558ddba6b1888a5aeae9576ac420515493ad` | Ubuntu Python 3.11.16; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed in 1.19s, no broken requirements | Docs-only PR #3, not BUD-01 code evidence |
| PR #3 previous head `82b482d2bd868042231b852a3709537e42e286d1`, Actions [run 36117923645](https://github.com/head-blini/ai-asset-copilot/actions/runs/36117923645), PR merge checkout `b4367e63f54c16f6de8339ecff0f6f7c13d99e20` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed in 1.34s, no broken requirements; run state rechecked 2026-09-25 | Historical result for prior Budget document head; this document revision needs its own CI result |
| PR #2 head `d1beb1b8e0cfc25371ed2dc6954cd85bf18e12f0`, Actions [run 36120513566](https://github.com/head-blini/ai-asset-copilot/actions/runs/36120513566), PR merge checkout `c1d2839736291a9852db627435dc887b73868b10` | Ubuntu Python 3.11.16; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 265 passed in 2.42s, no broken requirements; log checked | P4-05 candidate only; not Budget implementation or Phase 4 completion |
| PR #1 current head `9cd1a0f52b457352fca7d76500daac57d9dbdd25`, GitHub Actions [run 36101472221](https://github.com/head-blini/ai-asset-copilot/actions/runs/36101472221), PR merge checkout `3d1aa49128bfaaab40969410266cc79660c89562` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` (2026-09-25) | **SUCCESS**: 133 passed in 1.24s, no broken requirements; log checked | PR #1 head and CI merge checkout are different SHAs; not Budget/P4 code evidence |
| PR #1 reviewed head `c37ca413d600adf1b178c50d6109123771209900` | macOS, repository `.venv` Python 3.11.15, pytest 9.1.1; `.venv/bin/python -m pytest`, `.venv/bin/python -m pip check`, `git diff --check` (2026-09-25) | **133 passed**, 0 failed/skipped, 0.31s; no broken requirements; diff check passed | Local result for this exact head |
| GitHub Actions PR #1 [run 35697851552](https://github.com/head-blini/ai-asset-copilot/actions/runs/35697851552) on `c37ca413d600adf1b178c50d6109123771209900` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed, 0 failed/skipped; no broken requirements | CI result for this exact head; run logs checked |
| main base `0071d2b074be686392348ad6fbeec47d596e90de` in clean R0 worktree before edits | Repository `.venv` Python 3.11.9, pytest 9.1.1; `.venv/bin/python -m pytest` | 133 collected, **133 passed**, 0 failed, 0 skipped, 0.76s | Main Phase 0–3 code only |
| candidate HEAD `089ee027bbdb03557d83cb081e0acd35694c23fe` in original candidate worktree | Same `.venv`; `.venv/bin/python -m pytest` | 219 collected, **219 passed**, 0 failed, 0 skipped, 0.98s | Candidate only; does not close P4-05/06/07/09 |
| Earlier GitHub Actions PR #1 [run 35697243360](https://github.com/head-blini/ai-asset-copilot/actions/runs/35697243360) on `a19bc9a1b30efb1b47c8affba157cb5648a7fccf` | Ubuntu 24.04, Python 3.11.16, pytest 9.1.1; editable dev install, `python -m pytest`, `python -m pip check` | **SUCCESS**: 133 passed, 0 failed/skipped, pip check clean | Historical evidence for the earlier head |

No API key, real account, live Broker, or external Market Data call is required by these pytest runs. Local tests and GitHub Actions are separate results tied to their exact SHA. PR #1's `c37ca41` rows are historical; its actual current head is `9cd1a0f` with separate run `36101472221`. PR #3's `82b482d` run is historical after this new document revision.

## Candidate Phase 4 acceptance review

The [ROADMAP P4 gate](ROADMAP.md#phase-4-canonical-acceptance-criteria) retains the original main acceptance scope. The candidate review at `089ee02` records P4-01/02/03/04/08 as passing its historical local tests. **P4-05 IN REVIEW:** Core/Growth classification and full Target/Range evaluation are proposed in separate [PR #2](https://github.com/head-blini/ai-asset-copilot/pull/2), not accepted or merged. **P4-06 OPEN:** immutable Policy content, change history, version/effective-time linkage and historical replay. **P4-07 OPEN:** enforceable human approval and AI write/Risk bypass denial. **P4-09 OPEN:** all conditions, review, main merge and status update. No individual PASS means full-portfolio compliance, and candidate code remains unmerged. This Budget document change neither reviews nor modifies P4-05 code.

## Budget / Cashflow scope request and evidence

| Evidence type | 2026-09-25 observation | Boundary |
| --- | --- | --- |
| User request | Personal income-based monthly Budget/Cashflow Planning, actuals comparison, savings and investment funding proposals added to product scope | Requested scope, not feature completion or permission to move funds |
| Code inspection | main's `domain/models.py` has investment-account `DEPOSIT`/`WITHDRAW`; `storage/sqlite.py` and tests cover that Ledger. No personal income/expense or budget calculator found on main | Existing investment Ledger cannot be represented as a personal cashflow Ledger without a new contract |
| Document proposal | PROJECT_SPEC, ARCHITECTURE and ROADMAP on PR #3 define BUD-01~04 and financial/authority boundaries | R0 and PR #3 are unmerged; product decision does not grant financial authority |
| Code candidate | This branch adds a pure `budget.monthly` API, synthetic manual input and offline report | Candidate only, not main, no DB/provider/approval/transfer/order connection |
| Tests and CI | Exact-sha local code test above; PR #1/#2/#3 CI are separate. BUD-01 PR-head CI must be checked after publication | Documentation review, code inspection, local tests and CI are distinct evidence |

The user subsequently identified **home purchase and retirement** as asset-growth purposes. Goal amount, timing, loss tolerance and personalized strategy remain unknown; “more money is better” is not risk approval. Mobile/PC web is the planned primary interface, Telegram is limited to alerts and allowed simple lookups, and a separate Mac mini program is the initial execution setting. This is a product decision, not an implemented web service, deployment, approval system or live-money permission. BUD-01 must report known cashflow when goals are undefined and must not call all remaining cash investable.

BUD-01 has an **IN REVIEW candidate / NOT DONE**; BUD-02~04 are **PLANNED / NOT IMPLEMENTED**. BUD-01 is independent of P4-06/07; its input/output, offline example and test gates remain in [ROADMAP](ROADMAP.md#bud-01-다음-코드-작업-계약). User policy amounts and approval settings remain unset in [OD-15~19](../PROJECT_SPEC.md#15-open-decisions). No bank, card, Toss, live account, web, approval, transfer or order capability is inferred from this candidate.

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

R0 review PR [#1](https://github.com/head-blini/ai-asset-copilot/pull/1) is open against `main` and remains unmerged. Its current head `9cd1a0f` has the successful run `36101472221`. Review M1 ordering and input/report dependencies before adopting the proposed sequence adjustment.

The P4-05 candidate [PR #2](https://github.com/head-blini/ai-asset-copilot/pull/2) is in review without changing the Phase 4 gate. The next existing Policy code task after its review is a small design review and P4-06/07 implementation for policy history, human approval and AI write denial. Preserve the candidate branch history; after R0 merges, reconcile latest main normally, resolve documentation conflicts and rerun tests before Policy integration. R0's M1 ordering still needs review. Separately, review BUD-01's code and offline examples; this is not a replacement for P4-05 or permission to start BUD-02/03. Phase 4 remains blocked until P4-09; do not begin Phase 5 or enable live orders.
