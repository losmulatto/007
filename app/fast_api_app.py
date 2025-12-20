# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
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


def _extract_preview(file_path: Path, extension: str) -> tuple[Optional[str], bool]:
    try:
        if extension == ".txt":
            return _read_text_preview(file_path)
        if extension == ".docx":
            text = _extract_docx_text(file_path)
            if len(text) > UPLOAD_PREVIEW_CHARS:
                return text[:UPLOAD_PREVIEW_CHARS], True
            return text, False
    except Exception:
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
app.title = "samha-infra"
app.description = "API for interacting with the Agent samha-infra"


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
