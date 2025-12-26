**Name**: Samha Infra (Agent Stack)

**Product Vision**:
Samha is an advanced RAG-based agentic system designed to assist users (professionals and citizens) with complex queries related to social services (SOTE). It leverages the **Google Agent Development Kit (ADK)** to orchestrate multiple specialized agents (Hankesuunnittelija, Ammattilaiset, etc.) and integrates deeply with Google Cloud Vertex AI for search and reasoning.

## Core Capabilities
- **Multi-Agent Orchestration**: Specialized sub-agents for different domains (Contracts, QA, Professionals, Volunteers).
- **RAG & Knowledge Retrieval**: Ingestion pipeline for PDFs/Docs -> Vertex AI Search / Vector Search.
- **Strict Quality Assurance**: "Hard Gates" and "Release Gate" evaluation pipelines (`eval_comprehensive.py`).
- **Observability**: Cloud Trace & BigQuery logging for prompt/response telemetry.
- **Deployment**: Fully automated CI/CD to Google Cloud Run via Terraform.

## Target Audience
- **SOTE Professionals**: Seeking accurate, cited information from huge knowledge bases.
- **Developers**: Maintaining and extending the agent capabilities.
