from enum import Enum

class ToolId(str, Enum):
    # Web & Research
    RETRIEVE_DOCS = "retrieve_docs"
    SEARCH_WEB = "search_web"
    SEARCH_VERIFIED = "search_verified_sources"
    SEARCH_LEGAL = "search_legal_sources"
    SEARCH_NEWS = "search_news"
    
    # Documents & Data
    READ_PDF = "read_pdf_content"
    GET_PDF_META = "get_pdf_metadata"
    READ_EXCEL = "read_excel"
    READ_CSV = "read_csv"
    ANALYZE_EXCEL = "analyze_excel_summary"
    LIST_EXCEL_SHEETS = "list_excel_sheets"
    PYTHON_INTERPRETER = "python_interpreter"
    
    # Advanced / Admin
    PROCESS_MEETING = "process_meeting_transcript"
    GENERATE_CHART = "generate_data_chart"
    SCHEDULE_MEETING = "schedule_samha_meeting"
    GENERATE_IMAGE = "generate_image"
    
    # Archive
    SAVE_ARCHIVE = "save_to_archive"
    SEARCH_ARCHIVE = "search_archive"
    GET_ARCHIVED = "get_archived_content"
    
    # Communication
    TRANSLATE = "translate_text"
    FORMAT_SOCIAL = "format_social_post"
    CREATE_NEWSLETTER = "create_newsletter_section"
    
    # System
    TRANSFER = "transfer_to_agent"
