# Copyright 2025 Samha
"""
PDF-lukutyökalut - PDF Reading Tools
"""

import os
from typing import Optional
from pypdf import PdfReader

def read_pdf_content(file_path: str, max_pages: Optional[int] = None) -> str:
    """
    Lukee PDF-tiedoston sisällön ja palauttaa tekstin. 
    Käytä tätä kun tarvitset tietoa pitkistä ohjeista, raportteista tai dokumenteista.
    
    Args:
        file_path: Polku PDF-tiedostoon.
        max_pages: Maksimimäärä sivuja joita luetaan (oletus: kaikki).
    
    Returns:
        str: PDF:n teksti tai virheilmoitus.
    """
    if not os.path.exists(file_path):
        return f"❌ Virhe: Tiedostoa ei löydy polusta: {file_path}"
    
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        pages_to_read = min(total_pages, max_pages) if max_pages else total_pages
        
        content = []
        content.append(f"## PDF-tiedosto luettu: {os.path.basename(file_path)}")
        content.append(f"- Sivuja yhteensä: {total_pages}")
        content.append(f"- Luettu sivuja: {pages_to_read}")
        content.append("\n--- SISÄLTÖ ALKAA ---\n")
        
        for i in range(pages_to_read):
            page = reader.pages[i]
            text = page.extract_text()
            if text:
                content.append(f"\n[SIVU {i+1}]\n{text}")
        
        content.append("\n--- SISÄLTÖ PÄÄTTYY ---")
        
        return "\n".join(content)
    except Exception as e:
        return f"❌ Virhe PDF:n lukemisessa: {str(e)}"

def get_pdf_metadata(file_path: str) -> str:
    """
    Palauttaa PDF-tiedoston perustiedot (sivumäärä, otsikko, kirjoittaja).
    
    Args:
        file_path: Polku PDF-tiedostoon.
    
    Returns:
        str: PDF:n metatiedot markdown-muodossa.
    """
    if not os.path.exists(file_path):
        return f"❌ Virhe: Tiedostoa ei löydy polusta: {file_path}"
    
    try:
        reader = PdfReader(file_path)
        meta = reader.metadata
        
        info = [f"## PDF-metatiedot: {os.path.basename(file_path)}"]
        info.append(f"- Sivumäärä: {len(reader.pages)}")
        
        if meta:
            if meta.title: info.append(f"- Otsikko: {meta.title}")
            if meta.author: info.append(f"- Tekijä: {meta.author}")
            if meta.subject: info.append(f"- Aihe: {meta.subject}")
            if meta.creator: info.append(f"- Luotu ohjelmalla: {meta.creator}")
        
        return "\n".join(info)
    except Exception as e:
        return f"❌ Virhe metatietojen lukemisessa: {str(e)}"
