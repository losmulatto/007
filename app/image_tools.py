# Copyright 2025 Samha
"""
Image Generation Tools using Vertex AI Imagen
"""

import os
import datetime
from typing import Optional
import google.auth
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

# Initialize Vertex AI
credentials, project_id = google.auth.default()
vertexai.init(project=project_id, location="us-central1")

def generate_samha_image(
    prompt: str, 
    aspect_ratio: str = "1:1",
    output_name: Optional[str] = None
) -> str:
    """
    Luo kuvan tekoälyllä Samhan viestintään. Tukee eri kuvasuhteita.
    
    Args:
        prompt: Kuvaus kuvasta jota halutaan luoda (englanniksi tai suomeksi).
        aspect_ratio: Kuvasuhde: '1:1' (Insta), '16:9' (Bannere), '9:16' (Stories).
        output_name: Toivottu tiedostonimi (ilman päätettä).
    
    Returns:
        str: Tiedostopolku luotuun kuvaan tai virheilmoitus.
    """
    try:
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        # Samha context enrichment for prompt
        enriched_prompt = f"{prompt}. Professional, warm, community-focused, modern clean style."
        
        # Determine number of images and aspect ratio
        # Note: Imagen 3 might have specific param names in SDK
        response = model.generate_images(
            prompt=enriched_prompt,
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            add_watermark=False,
        )
        
        if not response.images:
            return "❌ Virhe: Kuvan generointi epäonnistui (ei kuvia vastauksessa)."
            
        # Save image
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = output_name if output_name else f"samha_gen_{timestamp}"
        
        # Ensure data folder exists
        output_dir = "archive/generated_images"
        os.makedirs(output_dir, exist_ok=True)
        
        file_path = os.path.join(output_dir, f"{name}.png")
        response.images[0].save(location=file_path, include_generation_parameters=False)
        
        return f"✅ Kuva generoitu onnistuneesti!\n**Polku**: {file_path}\n**Kuvasuhde**: {aspect_ratio}"
        
    except Exception as e:
        return f"❌ Virhe kuvan generoinnissa: {str(e)}"
