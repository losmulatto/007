"""
Cloud SQL Archive Service for Samha.

Uses PostgreSQL (Cloud SQL) for metadata storage and GCS for content.
Replaces local SQLite for production reliability.
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Optional

# Import base classes
from app.archive import (
    ArchiveEntry,
    ArchiveSearchQuery,
    ArchiveSearchResult,
    ArchiveService,
)


class CloudSQLArchiveService(ArchiveService):
    """
    Cloud SQL (PostgreSQL) backed archive service.
    
    Uses:
    - PostgreSQL for metadata (via Cloud SQL)
    - GCS for full content storage (same as GCSArchiveService)
    """
    
    def __init__(
        self,
        connection_name: str,
        database: str = "samha_archive",
        user: str = "samha_app",
        password: str = None,
        ip: str = None,
        gcs_bucket: str = None,
    ):
        self.connection_name = connection_name
        self.database = database
        self.user = user
        self.password = password
        self.ip = ip
        self.gcs_bucket = gcs_bucket
        
        # Initialize GCS client if bucket provided
        self.bucket = None
        if gcs_bucket:
            from google.cloud import storage
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(gcs_bucket)
            self.prefix = os.environ.get("ARCHIVE_GCS_PREFIX", "archive/")
        
        self._init_db()
        print(f"CloudSQLArchiveService initialized: {connection_name}")
    
    def _get_connection(self):
        """Get a database connection."""
        import pg8000
        
        if self.ip:
            return pg8000.connect(
                host=self.ip,
                port=5432,
                database=self.database,
                user=self.user,
                password=self.password,
            )
        
        socket_path = f"/cloudsql/{self.connection_name}"
        return pg8000.connect(
            unix_sock=f"{socket_path}/.s.PGSQL.5432",
            database=self.database,
            user=self.user,
            password=self.password,
        )
    
    def _init_db(self):
        """Initialize database schema."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id VARCHAR(100) PRIMARY KEY,
                    trace_id VARCHAR(100),
                    title TEXT NOT NULL,
                    summary TEXT,
                    document_type VARCHAR(50),
                    program VARCHAR(50),
                    project VARCHAR(100),
                    tags TEXT,
                    audience VARCHAR(100),
                    language VARCHAR(10),
                    channel VARCHAR(50),
                    status VARCHAR(20),
                    qa_decision VARCHAR(20),
                    qa_report_id VARCHAR(100),
                    agent_name VARCHAR(100),
                    prompt_packs TEXT,
                    version INTEGER DEFAULT 1,
                    parent_id VARCHAR(100),
                    created_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE,
                    word_count INTEGER,
                    artifact_path TEXT
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_document_type ON entries(document_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_program ON entries(program)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at)")
            
            conn.commit()
            cursor.close()
            conn.close()
            print("Cloud SQL schema initialized")
            
        except Exception as e:
            print(f"Error initializing Cloud SQL schema: {e}")
            raise
    
    def save(self, entry: ArchiveEntry) -> str:
        """Save archive entry to Cloud SQL + GCS."""
        artifact_path = None
        if self.bucket:
            gcs_path = f"{self.prefix}{entry.id}.json"
            blob = self.bucket.blob(gcs_path)
            content_json = entry.model_dump_json(indent=2)
            blob.upload_from_string(content_json, content_type="application/json")
            artifact_path = f"gs://{self.gcs_bucket}/{gcs_path}"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO entries (
                id, trace_id, title, summary, document_type, program, project,
                tags, audience, language, channel, status, qa_decision, qa_report_id,
                agent_name, prompt_packs, version, parent_id, created_at, updated_at,
                word_count, artifact_path
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                updated_at = EXCLUDED.updated_at,
                version = entries.version + 1
        """, (
            entry.id, entry.trace_id, entry.title, entry.summary,
            entry.document_type, entry.program, entry.project,
            " ".join(entry.tags), entry.audience, entry.language, entry.channel,
            entry.status, entry.qa_decision, entry.qa_report_id,
            entry.agent_name, json.dumps(entry.prompt_packs), entry.version,
            entry.parent_id, entry.created_at.isoformat(), entry.updated_at.isoformat(),
            entry.word_count, artifact_path
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Saved to Cloud SQL: {entry.id}")
        return entry.id
    
    def get(self, entry_id: str) -> Optional[ArchiveEntry]:
        """Get archive entry by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT artifact_path FROM entries WHERE id = %s", (entry_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row or not row[0]:
            return None
        
        artifact_path = row[0]
        if artifact_path.startswith("gs://") and self.bucket:
            gcs_path = artifact_path.replace(f"gs://{self.gcs_bucket}/", "")
            blob = self.bucket.blob(gcs_path)
            if blob.exists():
                content = blob.download_as_text()
                data = json.loads(content)
                return ArchiveEntry(**data)
        
        return None
    
    def search(self, query: ArchiveSearchQuery) -> ArchiveSearchResult:
        """Search archive entries."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if query.document_type:
            conditions.append("document_type = %s")
            params.append(query.document_type)
        
        if query.program:
            conditions.append("program = %s")
            params.append(query.program)
        
        if query.project:
            conditions.append("project = %s")
            params.append(query.project)
        
        if query.status:
            conditions.append("status = %s")
            params.append(query.status)
        
        if query.agent_name:
            conditions.append("agent_name = %s")
            params.append(query.agent_name)
        
        if query.approved_only:
            conditions.append("qa_decision = 'approve'")
        
        if query.tags:
            for tag in query.tags:
                conditions.append("tags LIKE %s")
                params.append(f"%{tag}%")
        
        if query.query:
            conditions.append("(title ILIKE %s OR summary ILIKE %s OR tags ILIKE %s)")
            params.extend([f"%{query.query}%"] * 3)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        cursor.execute(f"SELECT COUNT(*) FROM entries WHERE {where_clause}", params)
        total_count = cursor.fetchone()[0]
        
        sql = f"""
            SELECT id, title, summary, document_type, program, project, tags, 
                   status, agent_name, created_at, word_count
            FROM entries WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([query.limit, query.offset])
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        entries = []
        for row in rows:
            entries.append(ArchiveEntry(
                id=row[0], title=row[1], summary=row[2] or "", content="",
                document_type=row[3] or "muu", program=row[4] or "muu",
                project=row[5] or "muu", tags=row[6].split() if row[6] else [],
                status=row[7] or "draft", agent_name=row[8] or "unknown",
                created_at=datetime.fromisoformat(str(row[9])) if row[9] else datetime.now(timezone.utc),
                word_count=row[10] or 0,
            ))
        
        return ArchiveSearchResult(entries=entries, total_count=total_count, query=query)
    
    def get_stats(self) -> dict:
        """Get archive statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM entries")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT document_type, COUNT(*) FROM entries GROUP BY document_type")
        by_type = dict(cursor.fetchall())
        
        cursor.execute("SELECT program, COUNT(*) FROM entries GROUP BY program")
        by_program = dict(cursor.fetchall())
        
        cursor.close()
        conn.close()
        
        return {"total_entries": total, "by_type": by_type, "by_program": by_program}
