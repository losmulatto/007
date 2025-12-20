from app.tool_ids import ToolId
from app.tools_base import (
    retrieve_docs,
    read_excel,
    read_csv,
    analyze_excel_summary,
    list_excel_sheets,
    python_interpreter,
)
from app.web_search import search_web, search_verified_sources, search_news, search_legal_sources
from app.pdf_tools import read_pdf_content, get_pdf_metadata
from app.advanced_tools import process_meeting_transcript, generate_data_chart, schedule_samha_meeting
from app.image_tools import generate_samha_image
from app.archive_tools import save_to_archive, search_archive, get_archived_content
from app.viestinta import translate_text, format_social_post, create_newsletter_section

TOOL_MAP = {
    ToolId.RETRIEVE_DOCS: retrieve_docs,
    ToolId.SEARCH_WEB: search_web,
    ToolId.SEARCH_VERIFIED: search_verified_sources,
    ToolId.SEARCH_LEGAL: search_legal_sources,
    ToolId.SEARCH_NEWS: search_news,
    ToolId.READ_PDF: read_pdf_content,
    ToolId.GET_PDF_META: get_pdf_metadata,
    ToolId.PROCESS_MEETING: process_meeting_transcript,
    ToolId.GENERATE_CHART: generate_data_chart,
    ToolId.SCHEDULE_MEETING: schedule_samha_meeting,
    ToolId.GENERATE_IMAGE: generate_samha_image,
    ToolId.SAVE_ARCHIVE: save_to_archive,
    ToolId.SEARCH_ARCHIVE: search_archive,
    ToolId.GET_ARCHIVED: get_archived_content,
    ToolId.READ_EXCEL: read_excel,
    ToolId.READ_CSV: read_csv,
    ToolId.ANALYZE_EXCEL: analyze_excel_summary,
    ToolId.LIST_EXCEL_SHEETS: list_excel_sheets,
    ToolId.PYTHON_INTERPRETER: python_interpreter,
    ToolId.TRANSLATE: translate_text,
    ToolId.FORMAT_SOCIAL: format_social_post,
    ToolId.CREATE_NEWSLETTER: create_newsletter_section,
}

# Reverse mapping for string resolution in callbacks
FUNCTION_NAME_TO_TOOL_ID = {
    "retrieve_docs": ToolId.RETRIEVE_DOCS,
    "search_web": ToolId.SEARCH_WEB,
    "search_verified_sources": ToolId.SEARCH_VERIFIED,
    "search_legal_sources": ToolId.SEARCH_LEGAL,
    "search_news": ToolId.SEARCH_NEWS,
    "read_pdf_content": ToolId.READ_PDF,
    "get_pdf_metadata": ToolId.GET_PDF_META,
    "process_meeting_transcript": ToolId.PROCESS_MEETING,
    "generate_data_chart": ToolId.GENERATE_CHART,
    "schedule_samha_meeting": ToolId.SCHEDULE_MEETING,
    "generate_samha_image": ToolId.GENERATE_IMAGE,
    "save_to_archive": ToolId.SAVE_ARCHIVE,
    "search_archive": ToolId.SEARCH_ARCHIVE,
    "get_archived_content": ToolId.GET_ARCHIVED,
    "read_excel": ToolId.READ_EXCEL,
    "read_csv": ToolId.READ_CSV,
    "analyze_excel_summary": ToolId.ANALYZE_EXCEL,
    "list_excel_sheets": ToolId.LIST_EXCEL_SHEETS,
    "python_interpreter": ToolId.PYTHON_INTERPRETER,
    "translate_text": ToolId.TRANSLATE,
    "format_social_post": ToolId.FORMAT_SOCIAL,
    "create_newsletter_section": ToolId.CREATE_NEWSLETTER,
    "transfer_to_agent": ToolId.TRANSFER
}
