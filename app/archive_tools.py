from app.archive import get_archive_service, ArchiveEntry, ArchiveSearchQuery

def save_to_archive(
    title: str,
    summary: str,
    content: str,
    document_type: str,
    program: str = "muu",
    project: str = "muu",
    tags: str = "",
    agent_name: str = "kirjoittaja",
    prompt_packs: str = "org_pack_v1",
) -> str:
    """Tallenna teksti arkistoon."""
    archive = get_archive_service()
    entry = ArchiveEntry(
        title=title,
        summary=summary[:500],
        content=content,
        document_type=document_type,
        program=program,
        project=project,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        agent_name=agent_name,
        prompt_packs=[p.strip() for p in prompt_packs.split(",") if p.strip()],
        status="draft",
    )
    entry_id = archive.save(entry)
    return f"Arkistoitu onnistuneesti. ID: {entry_id}"

def search_archive(
    query: str = "",
    document_type: str = "",
    program: str = "",
    project: str = "",
    tags: str = "",
    latest_only: bool = True,
    limit: int = 5,
) -> str:
    """Hae arkistosta."""
    allowed_types = {"hakemus", "raportti", "artikkeli", "koulutus", "some", "memo", "muu"}
    if document_type:
        doc_norm = document_type.strip().lower()
        if doc_norm not in allowed_types:
            # Fallback to broad search if type is not supported
            doc_norm = ""
        document_type = doc_norm
    archive = get_archive_service()
    search_query = ArchiveSearchQuery(
        query=query if query else None,
        document_type=document_type if document_type else None,
        program=program if program else None,
        project=project if project else None,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        latest_only=latest_only,
        limit=limit,
    )
    result = archive.search(search_query)
    if not result.entries: return "Ei tuloksia."
    output = f"Löytyi {result.total_count} tulosta:\n\n"
    for entry in result.entries:
        output += f"**{entry.title}** (ID: {entry.id})\n"
        output += f"- Tiivistelmä: {entry.summary[:100]}...\n\n"
    return output

def get_archived_content(entry_id: str) -> str:
    """Hae arkistoitu teksti ID:llä."""
    archive = get_archive_service()
    entry = archive.get(entry_id)
    if not entry: return f"Arkistokirjausta {entry_id} ei löytynyt."
    return f"# {entry.title}\n\n{entry.content}"
