# Asset Copilot — Agent Operating Rules

GitHub `head-blini/ai-asset-copilot` is the canonical project repository. Verify remote `main` and relevant candidate refs before planning, reviewing, implementing, or declaring completion. If access fails, record the limitation and do not call a local snapshot current remote state.

## Context and evidence

Before project work, read `AGENTS.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, relevant code and tests, branch ancestry, merge state, and verification evidence. Preserve and inspect uncommitted work before reconciliation. GitHub `main` is the merged baseline; a feature branch is a candidate. Document review, code review, a passing local test, a passing CI run, a merged change, and operational readiness are separate facts. Record the exact code SHA and environment for each test result. CI is pending until an actual run on the relevant head SHA finishes successfully.

Git state controls code truth, ROADMAP controls phase scope and completion gates, STATUS controls current phase and immediate work, and chat is supporting context. Reconcile contradictions explicitly. Do not silently copy candidate documentation into `main` or present candidate APIs as merged.

## Phase and documentation gates

Use the canonical Phase 0–13 sequence. The normal state path is `PLANNED -> NEXT -> IN_PROGRESS -> IN REVIEW -> DONE`; `IN REVIEW` and older `VERIFYING` mean not complete. Do not reduce acceptance criteria or transfer scope without an explicit, reviewed ROADMAP change. A feature phase is DONE only when its gate is met, relevant tests pass, review is complete, code is merged to `main`, and STATUS is updated. A documentation/CI PR may merge independently without closing a feature phase.

Update STATUS in the same change when a phase starts, reaches review, finds a blocker, closes, or changes immediate work or a major assumption. Update ROADMAP when scope, sequence, architecture constraints, milestones, or completion criteria materially change. Preserve completed history.

## Code and financial boundaries

Preserve ledger/state separation, deterministic replay, provider/broker abstractions, and source/time provenance. External prices, FX, broker state, and AI output are observations until deliberately ingested. Financial writes fail closed on ambiguity, stale data, reconciliation failure, duplicate risk, or missing required state. Add tests for new success, edge, and failure paths; use the project `.venv` when present for final verification. Prefer small phase-scoped changes.

AI may analyze and propose but cannot bypass application constraints, change human Policy, or bypass the independent Risk Engine. Broker work follows `research -> backtest -> paper trading -> broker adapter -> risk gate -> limited live trading`. No analysis path directly submits unrestricted live orders.

## Roles and reporting

ChatGPT supports overall design, priorities, critical review, and next-phase decisions. Codex implements, tests, refactors, and documents. These are development roles, not runtime components or approval credentials. Human approval is required where the product specification says so.

Report what changed, files changed, exact ref/environment/command/results for tests and CI, current phase, blockers, and the exact next task. Do not auto-merge a review PR or treat review approval as an operational deployment.
