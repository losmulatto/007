# Technology Stack

## Core Language & Runtime
- **Language**: Python 3.10+
- **Runtime Manager**: `uv` (Fast Python package installer)

## Agent Framework & AI
- **Framework**: Google ADK (`google-adk[eval]`)
- **Orchestration**: LangChain (`langchain-google-vertexai`, `langchain-community`)
- **LLM**: Gemini Pro (via Vertex AI)
- **Vector Store**: Vertex AI Vector Search / Vertex AI Search
- **Telemetry**: OpenTelemetry (`opentelemetry-instrumentation-google-genai`)

## Backend & API
- **Server**: FastAPI (`fastapi`, `uvicorn`) typically running on port 8080.
- **Database**: AsyncPG (PostgreSQL) if referenced, or Vector Stores.

## Infrastructure & DevOps
- **Cloud**: Google Cloud Platform (Cloud Run, Cloud Build, BigQuery, GCS).
- **IaC**: Terraform (in `deployment/` folder).
- **CI/CD**: Cloud Build (via `agent-starter-pack` CLI commands).

## Development & Quality Tools
- **Test Runner**: `pytest` (asyncio plugin enabled).
- **Linting**: `ruff` (Line length 88, configured in `pyproject.toml`).
- **Type Checking**: `mypy`.
- **Evaluation**: `eval_comprehensive.py` (Custom suite runner).
- **Automation**: `Makefile` (install, playground, deploy).

## Project Structure (Key Folders)
- `app/`: Core agent code (`agent.py` entry point).
- `contracts/`: JSON schemas for structured outputs.
- `api/`: FastAPI routes (`fast_api_app.py`).
- `notebooks/`: Prototyping and evaluation notebooks.
