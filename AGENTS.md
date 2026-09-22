# Asset Copilot — Agent Operating Rules

The connected GitHub repository `head-blini/ai-asset-copilot` is the canonical source of truth for project execution. Verify current remote refs before planning, reviewing, implementing, or deciding phase completion when access is available. Record any access limitation; do not present an unverified local snapshot as the latest remote state.

## Required context before work

Before implementing, reviewing, or planning any project change, read:

1. Root `AGENTS.md`
2. `docs/ROADMAP.md`
3. `docs/STATUS.md`
4. Relevant source code and tests
5. Branch/commit ancestry, merge state, and verification evidence

Do not rely on an older chat summary when repository state is available.

## Source of truth

- GitHub `main` is the merged code baseline. Remote feature branches are candidates, not evidence of completion.
- Preserve uncommitted local work and inspect it before reconciling it with remote documents.
- Git repository state is authoritative for code.
- `docs/ROADMAP.md` is authoritative for product sequence, phase scope, and completion gates.
- `docs/STATUS.md` is authoritative for current phase, verification state, blockers, and immediate next work.
- Chat conversations are supporting context only and must not silently override repository state.

If code, ROADMAP, STATUS, and a chat summary disagree, inspect the repository and explicitly reconcile the inconsistency before proceeding.

## Phase execution

Work on the current phase in `docs/STATUS.md` unless the user explicitly changes priorities.

Normal transition:

`PLANNED -> NEXT -> IN_PROGRESS -> IN REVIEW -> DONE`

`IN REVIEW` means NOT DONE; `VERIFYING` in older notes has the same non-complete meaning. Preserve the canonical Phase 0–13 numbering. Do not narrow acceptance criteria retrospectively to match an implementation. Scope transfers require explicit rationale, dependencies, and an authorized ROADMAP change.

A phase is not DONE just because implementation exists. It is DONE only after its completion gate in `docs/ROADMAP.md` is satisfied, relevant tests pass, review is complete, the change is merged to `main`, and `docs/STATUS.md` is updated.

Do not begin substantial work on the next phase while the current phase has unresolved correctness, safety, reconciliation, or merge blockers.

## Roles

- ChatGPT: overall design, priorities, critical review, implementation review, and next-phase decisions.
- Codex: implementation, tests, refactoring, and repository documentation.
- GitHub: the single official source for code and project state.

## Documentation updates

Update `docs/STATUS.md` in the same change whenever:

- a phase starts,
- implementation reaches verification,
- verification finds a blocker,
- a phase is merged/closed,
- a major implementation assumption changes,
- the immediate next task changes materially.

Update `docs/ROADMAP.md` only when phase scope, sequence, architecture constraints, milestones, or completion criteria materially change.

Do not rewrite completed history merely to make current work look cleaner.

## Coding and verification rules

- Preserve ledger/state separation and deterministic replay.
- Preserve provider/broker abstraction boundaries.
- Treat external prices, FX, broker state, and AI output as non-canonical observations unless explicitly persisted through a designed ingestion path.
- Financial writes must fail closed on ambiguity, stale data, reconciliation failure, duplicate risk, or missing required state.
- Add or update tests for success paths, edge cases, and failure paths introduced by a change.
- Check the preceding task's verification state before starting new work.
- Use the repository's project environment (`.venv` when present) for final verification.
- Prefer small phase-scoped commits over unrelated cleanup.

## AI and execution safety

The AI/copilot orchestration layer may analyze and propose actions, but it must not bypass application constraints or the independent trading risk engine.

For broker execution work, maintain the progression:

`research -> backtest -> paper trading -> broker adapter -> risk gate -> limited live trading`

Never shortcut directly from an analysis/recommendation path to unrestricted live order submission.

## End-of-task report

At the end of a meaningful task, report:

- what changed,
- tests/verification performed and their results,
- files changed,
- current phase/status,
- blockers or uncertainties,
- exact next task.

If the task changed project state, ensure `docs/STATUS.md` reflects that state before considering the task complete.
