# limitations under the License.

# -----------------------------------------------------------------------------
# PYDANTIC JSON SCHEMA FIX (Monkeypatch for FastAPI/OpenAPI)
# Must be at the VERY TOP to affect all imports
# -----------------------------------------------------------------------------
def _make_opaque_for_pydantic_schema():
    try:
        from typing import Any, Dict
        import pydantic
        import httpx
        from pydantic_core import core_schema

        def _get_core_schema(cls, _source, _handler):
            return core_schema.any_schema()
        
        for httpx_cls in [httpx.Client, httpx.AsyncClient]:
            if not hasattr(httpx_cls, "__get_pydantic_core_schema__"):
                httpx_cls.__get_pydantic_core_schema__ = classmethod(_get_core_schema)

        # Fix ADK classes
        try:
            from google.adk.models.base_llm import BaseLlm
            from google.adk import agents as adk_agents
            def __get_pydantic_json_schema__(cls, _core_schema: Any, handler: Any) -> Dict[str, Any]:
                return {"type": "object", "title": cls.__name__}
            
            classes_to_fix = [BaseLlm]
            for attr in ["Agent", "LlmAgent", "BaseAgent"]:
                if hasattr(adk_agents, attr):
                    classes_to_fix.append(getattr(adk_agents, attr))
            for cls in classes_to_fix:
                if not hasattr(cls, "__get_pydantic_json_schema__"):
                    cls.__get_pydantic_json_schema__ = classmethod(__get_pydantic_json_schema__)
        except Exception:
            pass
    except Exception:
        pass

_make_opaque_for_pydantic_schema()

import os
import re
import uuid
from urllib.parse import quote
from pathlib import Path
from typing import Optional
import zipfile
import xml.etree.ElementTree as ElementTree

import google.auth
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.env import load_env

load_env()

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["*"]
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_ROOT = Path(os.environ.get("UPLOAD_DIR", os.path.join(AGENT_DIR, "uploads")))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_PREVIEW_CHARS = int(os.environ.get("UPLOAD_PREVIEW_CHARS", "12000"))
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}


def _sanitize_segment(value: Optional[str]) -> str:
    if not value:
        return "anon"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return safe or "anon"


def _extract_docx_text(file_path: Path) -> str:
    with zipfile.ZipFile(file_path) as docx_zip:
        with docx_zip.open("word/document.xml") as xml_file:
            tree = ElementTree.parse(xml_file)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for para in tree.findall(".//w:p", namespace):
        texts = [node.text for node in para.findall(".//w:t", namespace) if node.text]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _read_text_preview(file_path: Path) -> tuple[str, bool]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        content = handle.read(UPLOAD_PREVIEW_CHARS + 1)
    truncated = len(content) > UPLOAD_PREVIEW_CHARS
    return content[:UPLOAD_PREVIEW_CHARS], truncated


def _extract_pdf_text(file_path: Path) -> str:
    """Extract text from PDF using pymupdf."""
    try:
        import pymupdf  # pip install pymupdf
        doc = pymupdf.open(str(file_path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except ImportError:
        # Fallback: try pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                text_parts = []
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
                return "\n".join(text_parts)
        except ImportError:
            return ""
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""


def _extract_preview(file_path: Path, extension: str) -> tuple[Optional[str], bool]:
    try:
        if extension == ".txt":
            return _read_text_preview(file_path)
        if extension == ".docx":
            text = _extract_docx_text(file_path)
            if len(text) > UPLOAD_PREVIEW_CHARS:
                return text[:UPLOAD_PREVIEW_CHARS], True
            return text, False
        if extension == ".pdf":
            text = _extract_pdf_text(file_path)
            if text:
                if len(text) > UPLOAD_PREVIEW_CHARS:
                    return text[:UPLOAD_PREVIEW_CHARS], True
                return text, False
            return None, False
    except Exception as e:
        print(f"Preview extraction error: {e}")
        return None, False
    return None, False

# Cloud SQL session configuration
db_user = os.environ.get("DB_USER", "postgres")
db_name = os.environ.get("DB_NAME", "postgres")
db_pass = os.environ.get("DB_PASS")
instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

session_service_uri = None
if instance_connection_name and db_pass:
    # Use Unix socket for Cloud SQL
    # URL-encode username and password to handle special characters (e.g., '[', '?', '#', '$')
    # These characters can cause URL parsing errors, especially '[' which triggers IPv6 validation
    encoded_user = quote(db_user, safe="")
    encoded_pass = quote(db_pass, safe="")
    # URL-encode the connection name to prevent colons from being misinterpreted
    encoded_instance = instance_connection_name.replace(":", "%3A")

    session_service_uri = (
        f"postgresql+asyncpg://{encoded_user}:{encoded_pass}@"
        f"/{db_name}"
        f"?host=/cloudsql/{encoded_instance}"
    )

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=True,
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.title = "samha-infra"
app.description = "API for interacting with the Agent samha-infra"

# -----------------------------------------------------------------------------
# OPENAPI SAFEGUARD
# -----------------------------------------------------------------------------
from fastapi.openapi.utils import get_openapi
import traceback

def custom_openapi():
    """Custom OpenAPI generator that catches schema generation errors."""
    if app.openapi_schema:
        return app.openapi_schema
    try:
        openapi_schema = get_openapi(
            title=app.title,
            version="1.0.0",
            description=app.description,
            routes=app.routes,
        )
        # Prune problematic fields from the generated schema if needed
        # (For now, just ensuring it doesn't crash the whole app)
    except Exception as e:
        print(f"CRITICAL: OpenAPI schema generation failed: {e}")
        # Return a minimal valid OpenAPI schema so the UI doesn't 500
        openapi_schema = {
            "openapi": "3.0.0",
            "info": {
                "title": app.title,
                "version": "1.0.0",
                "description": "API (OpenAPI generation failed, but service is running)"
            },
            "paths": {}
        }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
) -> dict[str, object]:
    filename = file.filename or "upload"
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tiedostotyyppi ei ole tuettu: {extension}",
        )

    target_dir = UPLOAD_ROOT
    if user_id or session_id:
        parts = []
        if user_id:
            parts.append(_sanitize_segment(user_id))
        if session_id:
            parts.append(_sanitize_segment(session_id))
        target_dir = UPLOAD_ROOT.joinpath(*parts)

    target_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = _sanitize_segment(Path(filename).stem)
    unique_suffix = uuid.uuid4().hex[:8]
    stored_name = f"{safe_stem}-{unique_suffix}{extension}"
    target_path = target_dir / stored_name

    size_bytes = 0
    chunk_size = 1024 * 1024
    with open(target_path, "wb") as handle:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > MAX_UPLOAD_BYTES:
                handle.close()
                if target_path.exists():
                    target_path.unlink()
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Tiedosto on liian suuri. Maksimikoko on {MAX_UPLOAD_MB} MB."
                    ),
                )
            handle.write(chunk)

    preview_text, preview_truncated = _extract_preview(target_path, extension)

    return {
        "stored_path": str(target_path),
        "original_name": filename,
        "size_bytes": size_bytes,
        "mime_type": file.content_type,
        "preview_text": preview_text,
        "preview_truncated": preview_truncated,
    }


# =============================================================================
# ARCHIVE API ENDPOINTS
# =============================================================================

from app.archive import get_archive_service, ArchiveSearchQuery, ArchiveEntry
from typing import List

@app.get("/archive")
async def list_archive(
    document_type: Optional[str] = None,
    program: Optional[str] = None,
    project: Optional[str] = None,
    query: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List archived documents with optional filters."""
    archive = get_archive_service()
    
    search_query = ArchiveSearchQuery(
        document_type=document_type if document_type else None,
        program=program if program else None,
        project=project if project else None,
        query=query if query else None,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        latest_only=True,
        limit=limit,
        offset=offset,
    )
    
    result = archive.search(search_query)
    
    return {
        "entries": [
            {
                "id": e.id,
                "title": e.title,
                "summary": e.summary,
                "document_type": e.document_type,
                "program": e.program,
                "project": e.project,
                "tags": e.tags,
                "status": e.status,
                "agent_name": e.agent_name,
                "created_at": e.created_at.isoformat(),
                "word_count": e.word_count,
            }
            for e in result.entries
        ],
        "total_count": result.total_count,
    }


@app.get("/archive/stats")
async def get_archive_stats() -> dict:
    """Get archive statistics."""
    archive = get_archive_service()
    return archive.get_stats()


@app.get("/archive/folders")
async def list_archive_folders() -> dict:
    """List folder structure (grouped by type, program, project)."""
    archive = get_archive_service()
    return archive.list_folders()


@app.get("/archive/{entry_id}")
async def get_archive_entry(entry_id: str) -> dict:
    """Get a single archive entry by ID."""
    archive = get_archive_service()
    entry = archive.get(entry_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {
        "id": entry.id,
        "title": entry.title,
        "summary": entry.summary,
        "content": entry.content,
        "document_type": entry.document_type,
        "program": entry.program,
        "project": entry.project,
        "tags": entry.tags,
        "audience": entry.audience,
        "language": entry.language,
        "channel": entry.channel,
        "status": entry.status,
        "qa_decision": entry.qa_decision,
        "agent_name": entry.agent_name,
        "prompt_packs": entry.prompt_packs,
        "version": entry.version,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "word_count": entry.word_count,
    }


@app.delete("/archive/{entry_id}")
async def delete_archive_entry(entry_id: str) -> dict:
    """Delete an archive entry permanently."""
    archive = get_archive_service()
    success = archive.delete(entry_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"status": "deleted", "id": entry_id}


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
