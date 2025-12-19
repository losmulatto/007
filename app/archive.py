"""
Samha Knowledge + Output Archive

SQLite-pohjainen arkisto agentin tuotoksille.
- Tallentaa: hakemukset, raportit, artikkelit, koulutusrungot
- Metadata: trace_id, agent, packs, tags, status
- Haku: suodattava + full-text (otsikko, tiivistelmä, tagit)

Käyttö:
    from app.archive import ArchiveService
    
    archive = ArchiveService()
    entry_id = archive.save(entry)
    results = archive.search(document_type="hakemus", program="stea")
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, computed_field
import uuid


# =============================================================================
# ENUMS / LITERALS
# =============================================================================

DocumentType = Literal[
    "hakemus",       # Stea, Erasmus+
    "raportti",      # Vuosikertomus, väliraportti
    "artikkeli",     # Blogi, julkaisu
    "koulutus",      # Koulutusrunko, työpaja
    "some",          # Some-postaukset
    "memo",          # Sisäinen muistio
    "muu"
]

Program = Literal["stea", "erasmus", "muu"]

Project = Literal[
    "koutsi",
    "jalma", 
    "icat",
    "paikka_auki",
    "muu"
]

ArchiveStatus = Literal[
    "draft",        # Keskeneräinen
    "ready",        # Valmis julkaisuun
    "published",    # Julkaistu
    "archived"      # Arkistoitu (ei aktiivinen)
]

QADecision = Literal["approve", "needs_revision", "reject"]


# =============================================================================
# ARCHIVE ENTRY MODEL
# =============================================================================

class ToolCallRecord(BaseModel):
    """Työkalu-kutsu arkistointia varten."""
    tool_name: str
    status: Literal["success", "error"]
    latency_ms: Optional[int] = None


class ArchiveEntry(BaseModel):
    """Arkistoitu artefakti."""
    
    # Identification
    id: str = Field(default_factory=lambda: f"art_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}")
    trace_id: Optional[str] = Field(None, description="Session trace ID")
    
    # Content
    title: str = Field(..., description="Otsikko")
    summary: str = Field(..., max_length=500, description="Tiivistelmä max 500 merkkiä")
    content: str = Field(..., description="Täysi sisältö")
    
    # Classification
    document_type: DocumentType = Field(..., description="Dokumenttityyppi")
    program: Program = Field("muu", description="Ohjelma: stea, erasmus, muu")
    project: Project = Field("muu", description="Hanke")
    tags: List[str] = Field(default_factory=list, description="Tagit hakua varten")
    
    # Audience
    audience: str = Field("sisäinen", description="Kohdeyleisö")
    language: str = Field("fi", description="Kieli")
    channel: Optional[str] = Field(None, description="Kanava: web, some, print")
    
    # Status
    status: ArchiveStatus = Field("draft")
    qa_decision: Optional[QADecision] = Field(None)
    qa_report_id: Optional[str] = Field(None, description="Linkki QA-raporttiin")
    
    # Provenance (mistä tuli)
    agent_name: str = Field(..., description="Tuottanut agentti")
    prompt_packs: List[str] = Field(default_factory=list, description="Käytetyt prompt-paketit")
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Versioning
    version: int = Field(1, description="Versio, kasvaa päivityksessä")
    parent_id: Optional[str] = Field(None, description="Edellinen versio")
    
    @computed_field
    @property
    def word_count(self) -> int:
        return len(self.content.split())
    
    @computed_field
    @property
    def tags_str(self) -> str:
        """Tagit stringinä hakua varten."""
        return " ".join(self.tags)


class ArchiveSearchQuery(BaseModel):
    """Arkistohakukysely."""
    
    # Filters
    document_type: Optional[DocumentType] = None
    program: Optional[Program] = None
    project: Optional[Project] = None
    status: Optional[ArchiveStatus] = None
    tags: Optional[List[str]] = None
    agent_name: Optional[str] = None
    
    # Date range
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    # Options
    latest_only: bool = Field(False, description="Vain uusin per title")
    approved_only: bool = Field(False, description="Vain qa_decision=approve")
    
    # Full-text search
    query: Optional[str] = Field(None, description="Hakusana: otsikko, tiivistelmä, tagit")
    
    # Pagination
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class ArchiveSearchResult(BaseModel):
    """Hakutulos."""
    entries: List[ArchiveEntry]
    total_count: int
    query: ArchiveSearchQuery


# =============================================================================
# ARCHIVE SERVICE
# =============================================================================

class ArchiveService:
    """SQLite-pohjainen arkistopalvelu."""
    
    def __init__(self, db_path: str = "./archive/samha_archive.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.db_path.parent / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Luo taulut jos ei ole."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT,
                    document_type TEXT NOT NULL,
                    program TEXT DEFAULT 'muu',
                    project TEXT DEFAULT 'muu',
                    tags TEXT,  -- space-separated for FTS
                    audience TEXT,
                    language TEXT DEFAULT 'fi',
                    channel TEXT,
                    status TEXT DEFAULT 'draft',
                    qa_decision TEXT,
                    qa_report_id TEXT,
                    agent_name TEXT NOT NULL,
                    prompt_packs TEXT,  -- JSON array
                    version INTEGER DEFAULT 1,
                    parent_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    word_count INTEGER,
                    artifact_path TEXT  -- path to JSON file
                )
            """)
            
            # Full-text search virtual table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    id,
                    title,
                    summary,
                    tags,
                    content='entries',
                    content_rowid='rowid'
                )
            """)
            
            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_document_type ON entries(document_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_program ON entries(program)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project ON entries(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON entries(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON entries(created_at)")
            
            conn.commit()
    
    def save(self, entry: ArchiveEntry) -> str:
        """
        Tallenna arkistokirjaus.
        
        Returns:
            entry.id
        """
        # Save full content to JSON file
        artifact_path = self.artifacts_dir / f"{entry.id}.json"
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(entry.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        
        # Save metadata to SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO entries (
                    id, trace_id, title, summary, document_type, program, project,
                    tags, audience, language, channel, status, qa_decision, qa_report_id,
                    agent_name, prompt_packs, version, parent_id, created_at, updated_at,
                    word_count, artifact_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.trace_id,
                entry.title,
                entry.summary,
                entry.document_type,
                entry.program,
                entry.project,
                " ".join(entry.tags),
                entry.audience,
                entry.language,
                entry.channel,
                entry.status,
                entry.qa_decision,
                entry.qa_report_id,
                entry.agent_name,
                json.dumps(entry.prompt_packs),
                entry.version,
                entry.parent_id,
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
                entry.word_count,
                str(artifact_path)
            ))
            
            # Update FTS index
            conn.execute("""
                INSERT INTO entries_fts (id, title, summary, tags)
                VALUES (?, ?, ?, ?)
            """, (entry.id, entry.title, entry.summary, " ".join(entry.tags)))
            
            conn.commit()
        
        return entry.id
    
    def get(self, entry_id: str) -> Optional[ArchiveEntry]:
        """Hae yksittäinen arkistokirjaus ID:llä."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT artifact_path FROM entries WHERE id = ?",
                (entry_id,)
            ).fetchone()
            
            if not row:
                return None
            
            artifact_path = Path(row["artifact_path"])
            if not artifact_path.exists():
                return None
            
            with open(artifact_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return ArchiveEntry(**data)
    
    def search(self, query: ArchiveSearchQuery) -> ArchiveSearchResult:
        """
        Hae arkistosta suodattimilla ja/tai tekstihaulla.
        """
        conditions = []
        params = []
        
        # Build WHERE clause
        if query.document_type:
            conditions.append("document_type = ?")
            params.append(query.document_type)
        
        if query.program:
            conditions.append("program = ?")
            params.append(query.program)
        
        if query.project:
            conditions.append("project = ?")
            params.append(query.project)
        
        if query.status:
            conditions.append("status = ?")
            params.append(query.status)
        
        if query.agent_name:
            conditions.append("agent_name = ?")
            params.append(query.agent_name)
        
        if query.approved_only:
            conditions.append("qa_decision = 'approve'")
        
        if query.tags:
            for tag in query.tags:
                conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
        
        if query.date_from:
            conditions.append("created_at >= ?")
            params.append(query.date_from.isoformat())
        
        if query.date_to:
            conditions.append("created_at <= ?")
            params.append(query.date_to.isoformat())
        
        # Full-text search
        if query.query:
            conditions.append("""
                id IN (
                    SELECT id FROM entries_fts 
                    WHERE entries_fts MATCH ?
                )
            """)
            params.append(query.query)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Count total
            count_sql = f"SELECT COUNT(*) FROM entries WHERE {where_clause}"
            total_count = conn.execute(count_sql, params).fetchone()[0]
            
            # Fetch results
            if query.latest_only:
                # Get only latest version per title
                sql = f"""
                    SELECT artifact_path FROM entries 
                    WHERE {where_clause}
                    GROUP BY title
                    HAVING version = MAX(version)
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
            else:
                sql = f"""
                    SELECT artifact_path FROM entries 
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
            
            params.extend([query.limit, query.offset])
            rows = conn.execute(sql, params).fetchall()
        
        # Load full entries from JSON files
        entries = []
        for row in rows:
            artifact_path = Path(row["artifact_path"])
            if artifact_path.exists():
                with open(artifact_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries.append(ArchiveEntry(**data))
        
        return ArchiveSearchResult(
            entries=entries,
            total_count=total_count,
            query=query
        )
    
    def update(self, entry_id: str, updates: dict) -> Optional[ArchiveEntry]:
        """
        Päivitä arkistokirjaus (luo uuden version).
        
        Returns:
            New entry with incremented version
        """
        existing = self.get(entry_id)
        if not existing:
            return None
        
        # Create new version
        new_data = existing.model_dump()
        new_data.update(updates)
        new_data["version"] = existing.version + 1
        new_data["parent_id"] = existing.id
        new_data["id"] = f"art_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        new_data["updated_at"] = datetime.now(timezone.utc)
        
        new_entry = ArchiveEntry(**new_data)
        self.save(new_entry)
        
        return new_entry
    
    def list_latest(
        self,
        document_type: Optional[DocumentType] = None,
        project: Optional[Project] = None,
        limit: int = 10
    ) -> List[ArchiveEntry]:
        """Hae viimeisimmät arkistokirjaukset."""
        query = ArchiveSearchQuery(
            document_type=document_type,
            project=project,
            latest_only=True,
            limit=limit
        )
        result = self.search(query)
        return result.entries
    
    def get_stats(self) -> dict:
        """Arkiston tilastot."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            by_type = dict(conn.execute(
                "SELECT document_type, COUNT(*) FROM entries GROUP BY document_type"
            ).fetchall())
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM entries GROUP BY status"
            ).fetchall())
            by_program = dict(conn.execute(
                "SELECT program, COUNT(*) FROM entries GROUP BY program"
            ).fetchall())
        
        return {
            "total_entries": total,
            "by_type": by_type,
            "by_status": by_status,
            "by_program": by_program
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_archive_service: Optional[ArchiveService] = None


# =============================================================================
# GCS ARCHIVE SERVICE
# =============================================================================

class GCSArchiveService(ArchiveService):
    """
    Google Cloud Storage -pohjainen arkistopalvelu.
    
    Käyttää SQLite:tä metadatalle (lokaali) ja GCS:ää artifact-tiedostoille.
    Tuotannossa SQLite voidaan korvata Cloud SQL:llä.
    """
    
    def __init__(
        self, 
        bucket_name: str,
        db_path: str = "./archive/samha_archive.db",
        prefix: str = "artifacts/"
    ):
        from google.cloud import storage
        
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(bucket_name)
        
        # Initialize parent (SQLite for metadata)
        super().__init__(db_path=db_path)
        
        print(f"GCSArchiveService initialized with bucket: gs://{bucket_name}/{prefix}")
    
    def save(self, entry: ArchiveEntry) -> str:
        """
        Tallenna arkistokirjaus.
        - Metadata → SQLite (lokaali)
        - Content → GCS bucket
        """
        # Save full content to GCS
        gcs_path = f"{self.prefix}{entry.id}.json"
        blob = self.bucket.blob(gcs_path)
        
        content_json = entry.model_dump_json(indent=2)
        blob.upload_from_string(content_json, content_type="application/json")
        
        # Save metadata to SQLite with GCS path
        artifact_path = f"gs://{self.bucket_name}/{gcs_path}"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO entries (
                    id, trace_id, title, summary, document_type, program, project,
                    tags, audience, language, channel, status, qa_decision, qa_report_id,
                    agent_name, prompt_packs, version, parent_id, created_at, updated_at,
                    word_count, artifact_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.trace_id,
                entry.title,
                entry.summary,
                entry.document_type,
                entry.program,
                entry.project,
                " ".join(entry.tags),
                entry.audience,
                entry.language,
                entry.channel,
                entry.status,
                entry.qa_decision,
                entry.qa_report_id,
                entry.agent_name,
                json.dumps(entry.prompt_packs),
                entry.version,
                entry.parent_id,
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
                entry.word_count,
                artifact_path
            ))
            
            # Update FTS index
            conn.execute("""
                INSERT INTO entries_fts (id, title, summary, tags)
                VALUES (?, ?, ?, ?)
            """, (entry.id, entry.title, entry.summary, " ".join(entry.tags)))
            
            conn.commit()
        
        print(f"Saved to GCS: gs://{self.bucket_name}/{gcs_path}")
        return entry.id
    
    def get(self, entry_id: str) -> Optional[ArchiveEntry]:
        """Hae yksittäinen arkistokirjaus ID:llä GCS:stä."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT artifact_path FROM entries WHERE id = ?",
                (entry_id,)
            ).fetchone()
            
            if not row:
                return None
            
            artifact_path = row["artifact_path"]
            
            # Check if GCS path
            if artifact_path.startswith("gs://"):
                # Parse gs://bucket/path
                gcs_path = artifact_path.replace(f"gs://{self.bucket_name}/", "")
                blob = self.bucket.blob(gcs_path)
                
                if not blob.exists():
                    return None
                
                content = blob.download_as_text()
                data = json.loads(content)
            else:
                # Fall back to local file (for migration)
                local_path = Path(artifact_path)
                if not local_path.exists():
                    return None
                
                with open(local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            return ArchiveEntry(**data)
    
    def _load_entry_from_path(self, artifact_path: str) -> Optional[ArchiveEntry]:
        """Load entry from either GCS or local path."""
        try:
            if artifact_path.startswith("gs://"):
                gcs_path = artifact_path.replace(f"gs://{self.bucket_name}/", "")
                blob = self.bucket.blob(gcs_path)
                
                if not blob.exists():
                    return None
                
                content = blob.download_as_text()
                data = json.loads(content)
            else:
                local_path = Path(artifact_path)
                if not local_path.exists():
                    return None
                
                with open(local_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            return ArchiveEntry(**data)
        except Exception as e:
            print(f"Error loading {artifact_path}: {e}")
            return None
    
    def search(self, query: ArchiveSearchQuery) -> ArchiveSearchResult:
        """
        Hae arkistosta suodattimilla ja/tai tekstihaulla.
        Override to load from GCS.
        """
        conditions = []
        params = []
        
        # Build WHERE clause (same as parent)
        if query.document_type:
            conditions.append("document_type = ?")
            params.append(query.document_type)
        
        if query.program:
            conditions.append("program = ?")
            params.append(query.program)
        
        if query.project:
            conditions.append("project = ?")
            params.append(query.project)
        
        if query.status:
            conditions.append("status = ?")
            params.append(query.status)
        
        if query.agent_name:
            conditions.append("agent_name = ?")
            params.append(query.agent_name)
        
        if query.approved_only:
            conditions.append("qa_decision = 'approve'")
        
        if query.tags:
            for tag in query.tags:
                conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
        
        if query.date_from:
            conditions.append("created_at >= ?")
            params.append(query.date_from.isoformat())
        
        if query.date_to:
            conditions.append("created_at <= ?")
            params.append(query.date_to.isoformat())
        
        if query.query:
            conditions.append("""
                id IN (
                    SELECT id FROM entries_fts 
                    WHERE entries_fts MATCH ?
                )
            """)
            params.append(query.query)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            count_sql = f"SELECT COUNT(*) FROM entries WHERE {where_clause}"
            total_count = conn.execute(count_sql, params).fetchone()[0]
            
            if query.latest_only:
                sql = f"""
                    SELECT artifact_path FROM entries 
                    WHERE {where_clause}
                    GROUP BY title
                    HAVING version = MAX(version)
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
            else:
                sql = f"""
                    SELECT artifact_path FROM entries 
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """
            
            params.extend([query.limit, query.offset])
            rows = conn.execute(sql, params).fetchall()
        
        # Load entries from GCS or local
        entries = []
        for row in rows:
            entry = self._load_entry_from_path(row["artifact_path"])
            if entry:
                entries.append(entry)
        
        return ArchiveSearchResult(
            entries=entries,
            total_count=total_count,
            query=query
        )


def get_archive_service() -> ArchiveService:
    """
    Get or create archive service singleton.
    
    Uses GCS if ARCHIVE_GCS_BUCKET env var is set, otherwise local storage.
    """
    global _archive_service
    if _archive_service is None:
        bucket_name = os.environ.get("ARCHIVE_GCS_BUCKET")
        
        if bucket_name:
            print(f"Using GCS Archive: gs://{bucket_name}/")
            _archive_service = GCSArchiveService(
                bucket_name=bucket_name,
                prefix=os.environ.get("ARCHIVE_GCS_PREFIX", "archive/")
            )
        else:
            print("Using Local Archive: ./archive/")
            _archive_service = ArchiveService()
    
    return _archive_service

