import os
import google.auth
from google.genai import types as genai_types
from langchain_google_vertexai import VertexAIEmbeddings
from app.retrievers import get_retriever, get_compressor
from app.hard_gates import detect_gate_signals
import pandas as pd
from typing import Optional

# Shared LLM Configurations
LLM = "gemini-3-flash-preview"
LLM_TALOUS = "gemini-3-pro-preview"

LONG_OUTPUT_CONFIG = genai_types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=32768,
)

# Setup retriever for all agents
credentials, project_id = google.auth.default()
EMBEDDING_MODEL = "text-embedding-005"
LOCATION = "us-central1"

embeddings = VertexAIEmbeddings(
    project=project_id, location=LOCATION, model_name=EMBEDDING_MODEL
)

data_store_region = os.getenv("DATA_STORE_REGION", "global")
data_store_id = os.getenv("DATA_STORE_ID", "samha-knowledge-base")

retriever = get_retriever(
    project_id=project_id,
    data_store_id=data_store_id,
    data_store_region=data_store_region,
    embedding=embeddings,
    embedding_column="embedding",
    max_documents=10,
)

compressor = get_compressor(project_id=project_id)

def retrieve_docs(query: str) -> str:
    """
    Etsii tietoa Samhan sisäisestä tietokannasta (RAG).
    Käytä kun tarvitset tarkkoja faktoja: henkilöt, projektit, luvut, päivämäärät.
    """
    try:
        retrieved_docs = retriever.invoke(query)
        ranked_docs = compressor.compress_documents(documents=retrieved_docs, query=query)
        
        if not ranked_docs:
            return "Ei löytynyt dokumentteja tähän hakuun."
        
        formatted_parts = ["## Context provided:"]
        for doc in ranked_docs:
            content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
            formatted_parts.append(f"<Document>\n{content}\n</Document>")
        
        return "\n".join(formatted_parts)
    except Exception as e:
        return f"Retrieval error: {type(e).__name__}: {e}"

def read_excel(file_path: str, sheet_name: Optional[str] = None, max_rows: int = 5000) -> str:
    """Lukee Excel-tiedoston ja palauttaa datan markdown-taulukkona."""
    try:
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=max_rows)
        else:
            df = pd.read_excel(file_path, nrows=max_rows)
        total_rows = len(df)
        total_cols = len(df.columns)
        return f"## Excel luettu: {file_path}\nRows: {total_rows}, Cols: {total_cols}\n\n{df.to_markdown(index=False)}"
    except Exception as e:
        return f"Excel error: {e}"

def read_csv(file_path: str, max_rows: int = 5000) -> str:
    """Lukee CSV-tiedoston ja palauttaa datan markdown-taulukkona."""
    try:
        df = pd.read_csv(file_path, sep=None, engine='python', nrows=max_rows)
        return f"## CSV luettu: {file_path}\nRows: {len(df)}\n\n{df.to_markdown(index=False)}"
    except Exception as e:
        return f"CSV error: {e}"

def analyze_excel_summary(file_path: str, sheet_name: Optional[str] = None) -> str:
    """Laskee numeeristen sarakkeiden yhteenvedot."""
    try:
        if file_path.lower().endswith('.csv'):
            df = pd.read_csv(file_path, sep=None, engine='python')
        else:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if not numeric_cols: return "Ei numeerisia sarakkeita."
        summary = [f"## Yhteenveto: {file_path}"]
        for col in numeric_cols:
            summary.append(f"### {col}\n- Summa: {df[col].sum():,.2f}\n- Avg: {df[col].mean():,.2f}")
        return "\n".join(summary)
    except Exception as e:
        return f"Analysis error: {e}"

def list_excel_sheets(file_path: str) -> str:
    """Listaa Excel-välilehdet."""
    try:
        xl = pd.ExcelFile(file_path)
        return f"Välilehdet: {', '.join(xl.sheet_names)}"
    except Exception as e:
        return f"Excel error: {e}"
