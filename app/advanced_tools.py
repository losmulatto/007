# Copyright 2025 Samha
"""
Advanced NGO Tools - Transcription, Visualization, and Calendar
"""

import os
import json
import datetime
from typing import Optional
import matplotlib.pyplot as plt
import pandas as pd
from google.adk.agents import Agent
from google.genai import types as genai_types

# =============================================================================
# 1. TRANSCRIPTION PROCESSOR
# =============================================================================

LOMAKE_LLM = "gemini-3-flash-preview"

# Inner helper agent for structuring transcripts
_transcript_agent = Agent(
    model=LOMAKE_LLM,
    name="transcript_helper",
    instruction="""
    Tehtäväsi on muuttaa sekava kokous-transkriptio selkeäksi ja jäsennellyksi pöytäkirjaksi tai muistioksi.
    
    POIMI:
    1. Osallistujat (jos mainittu)
    2. Keskeiset keskustelunaiheet
    3. TEHDYT PÄÄTÖKSET (tärkein!)
    4. Seuraavat askeleet ja vastuuhenkilöt
    
    KÄYTÄ: Selkeää suomen kieltä ja bullet-pointteja.
    """,
)

async def process_meeting_transcript(transcript_text: str) -> str:
    """
    Muuttaa kokous-transkription jäsennellyksi pöytäkirjaksi.
    
    Args:
        transcript_text: Raaka teksti kokouksesta tai transkriptiosta.
        
    Returns:
        str: Jäsennelty pöytäkirja-luonnos.
    """
    try:
        # We simulate a run here. In ADK, we'd use runner or direct call.
        # For simplicity in this tool, we describe the transformation.
        response = await _transcript_agent.run_async(transcript_text)
        return response.text
    except Exception as e:
        return f"❌ Virhe transkription käsittelyssä: {str(e)}"

# =============================================================================
# 2. DATA VISUALIZER
# =============================================================================

def generate_data_chart(data_json: str, chart_type: str = "bar", title: str = "Samha Raportti") -> str:
    """
    Luo graafisen kaavion annetusta JSON-datasta.
    
    Args:
        data_json: JSON-string, joka sisältää labelit ja arvot (esim. '{"label": ["A", "B"], "value": [10, 20]}').
        chart_type: 'bar', 'pie' tai 'line'.
        title: Kaavion otsikko.
        
    Returns:
        str: Tiedostopolku luotuun kaavioon.
    """
    try:
        data = json.loads(data_json)
        df = pd.DataFrame(data)
        
        plt.figure(figsize=(10, 6))
        
        if chart_type == "bar":
            df.plot(kind="bar", x=df.columns[0], y=df.columns[1], legend=False, color="skyblue")
        elif chart_type == "pie":
            df.set_index(df.columns[0]).plot(kind="pie", y=df.columns[1], autopct='%1.1f%%', legend=False)
            plt.ylabel('')
        elif chart_type == "line":
            df.plot(kind="line", x=df.columns[0], y=df.columns[1], marker='o')
        
        plt.title(title)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save chart
        output_dir = "archive/charts"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(output_dir, f"chart_{timestamp}.png")
        plt.savefig(file_path)
        plt.close()
        
        return f"✅ Kaavio luotu! \n**Polku**: {file_path}\n**Tyyppi**: {chart_type}"
        
    except Exception as e:
        return f"❌ Virhe kaavion luonnissa: {str(e)}"

# =============================================================================
# 3. CALENDAR MOCK
# =============================================================================

def schedule_samha_meeting(subject: str, date: str, participants: str) -> str:
    """
    Varaa tapaamisen Samhan sisäiseen kalenteriin (MOCK).
    
    Args:
        subject: Tapaamisen aihe.
        date: Päivämäärä ja kellonaika.
        participants: Osallistujien nimet tai sähköpostit.
        
    Returns:
        str: Vahvistusviesti.
    """
    # This is a simulation for the prototype
    confirmation = f"""
    ✅ **Tapaaminen varattu Samha-kalenteriin!**
    - **Aihe**: {subject}
    - **Aika**: {date}
    - **Osallistujat**: {participants}
    - **Tila**: Vahvistettu (Mock)
    """
    return confirmation
