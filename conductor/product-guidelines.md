# Product Guidelines & Coding Standards

## Code Style
- **Formatter**: `ruff format .` (Black-compatible).
- **Linter**: `ruff check .` (Fixing imports, unused variables).
- **Types**: `mypy .` is mandatory. All public functions must have type hints.

## Architecture Patterns
- **Agent Definitions**: Define agents in `app/*_agent.py` or `registry`.
- **Dependency Injection**: Use `app.dependencies` module if available, or pass services explicitly to Agent constructors.
- **Config**: Use `pydantic-settings` or `os.getenv` via `.env` (loaded by `python-dotenv`).

## Workflow & Verification ("Non-Negotiables")
- **Playground First**: verify changes in `make playground` (interactive chat).
- **Eval Pipelines**:
    - **Regression**: `uv run python eval_comprehensive.py --suite full_eval_25.json` MUST pass before merge.
    - **Unit Tests**: `make test` (runs pytest).
- **Dependencies**: Always add with `uv add <package>`, never manual `pip install`.
- **Commits**: Descriptive messages, ideally linking to the Conductor Track/Task ID.

## Error Handling
- Use `logger` from `logging`.
- Catch specific exceptions, avoid bare `except:`.
- In Agents: Return structured error messages to the user if a tool fails, don't crash the stack.
