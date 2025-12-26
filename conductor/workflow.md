# Conductor Workflow

This project follows the **Spec -> Plan -> Implement** protocol.

## Protocol Steps

1. **New Track**: Create a new feature track.
   - Run: `/conductor:newTrack "Feature Name"`
   - *Fallback*: `mkdir conductor/tracks/track-00X && touch conductor/tracks/track-00X/{spec,plan}.md`

2. **Lock Spec & Plan**:
   - **Spec**: Define user impact, changes to `app/agent.py`, and new tools.
   - **Plan**: Detailed step-by-step dev plan.
   - **Review**: Ensure plan aligns with `product-guidelines.md` (e.g., "Add Eval Case").

3. **Implement**:
   - Execute one item from `plan.md`.
   - **Test-Driven**: Create a failing test or new eval case in `eval_comprehensive.py`.
   - Implement code.
   - **Verify**: `make playground` for manual check, `make test` for unit logic.
   - Mark item as `[x]` in `plan.md`.

4. **Verify**:
   - **Quick**: `make lint` (ruff + mypy)
   - **Deep**: `uv run python eval_comprehensive.py --suite full_eval_25.json`
   - **Interactive**: `make playground`

## Verification Commands
- **Unit Tests**: `make test`
- **Linting**: `make lint`
- **Local Server**: `make local-backend`
- **Interactive Chat**: `make playground`
- **Eval Suite**: `uv run python eval_comprehensive.py --suite full_eval_25.json`

## Commit Policy
- Commit after each *Task* logic completion.
- Format: `track-ID: Phase X Task Y - Description`
