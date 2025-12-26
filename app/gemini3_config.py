"""
Gemini 3 Configuration Module

Centralized configuration for Gemini 3 model selection and thinking levels.
Based on Google's official Gemini 3 prompting guide best practices.

Key principles:
- Don't lower temperature (keep at default 1.0)
- Use thinking_level to control quality/cost tradeoff
- Don't use thinking_budget and thinking_level together
"""
import os
from google.genai import types as genai_types
from google.genai.types import ThinkingConfig

# =============================================================================
# FEATURE FLAGS
# =============================================================================

USE_PRO = os.environ.get("SAMHA_USE_PRO", "false").lower() == "true"

# =============================================================================
# MODELS
# =============================================================================

MODEL_FLASH = "gemini-3-flash-preview"
MODEL_PRO = "gemini-3-pro-preview"


def pick_model(role: str) -> str:
    """
    Select model based on role and USE_PRO flag.
    
    Args:
        role: One of 'planner', 'research', 'writer', 'critic', 'default'
    
    Returns:
        Model name string
    """
    if USE_PRO:
        # Pro for critical agents when flag is on
        if role in ("writer", "critic", "finalizer"):
            return MODEL_PRO
    return MODEL_FLASH


# =============================================================================
# THINKING LEVEL PROFILES
# =============================================================================

# Thinking levels per Gemini 3 guide:
# - None: No extended thinking (fastest, cheapest)
# - "low": Light reasoning 
# - "medium": Moderate reasoning (default for most tasks)
# - "high": Deep reasoning (for complex evaluation/qa)

PROFILE_PLANNER = "planner"      # Routing, planning - minimal thinking needed
PROFILE_RESEARCH = "research"   # Search, summarization - low/medium thinking
PROFILE_WRITER = "writer"       # Long-form writing - medium thinking
PROFILE_CRITIC = "critic"       # Evaluation, scoring - high thinking
PROFILE_VALIDATOR = "validator" # Quick validation - low thinking


def get_thinking_config(profile: str) -> ThinkingConfig | None:
    """
    Get ThinkingConfig based on profile.
    
    Args:
        profile: One of the PROFILE_* constants
        
    Returns:
        ThinkingConfig or None (for no extended thinking)
    """
    thinking_levels = {
        PROFILE_PLANNER: None,  # No extended thinking for routing
        PROFILE_RESEARCH: ThinkingConfig(thinking_budget=1024),  # Light reasoning
        PROFILE_WRITER: ThinkingConfig(thinking_budget=2048),    # Moderate reasoning
        PROFILE_CRITIC: ThinkingConfig(thinking_budget=4096),    # Deep reasoning
        PROFILE_VALIDATOR: ThinkingConfig(thinking_budget=512),  # Quick validation
    }
    return thinking_levels.get(profile, None)


def gen_config(
    profile: str,
    max_output_tokens: int = 8192,
    include_thoughts: bool = False
) -> genai_types.GenerateContentConfig:
    """
    Generate content config for an agent based on profile.
    
    Key Gemini 3 best practices:
    - No temperature adjustment (keep at default 1.0)
    - Use thinking_level/budget for quality control
    
    Args:
        profile: One of the PROFILE_* constants
        max_output_tokens: Max tokens in response
        include_thoughts: Whether to include thinking in response
        
    Returns:
        GenerateContentConfig with appropriate settings
    """
    thinking_config = get_thinking_config(profile)
    
    # If we have thinking config and want to include thoughts
    if thinking_config and include_thoughts:
        thinking_config = ThinkingConfig(
            thinking_budget=thinking_config.thinking_budget,
            include_thoughts=True
        )
    
    config = genai_types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        # NOTE: No temperature set - keep at Gemini 3 default (1.0)
        # Lowering temperature can cause looping and quality degradation
    )
    
    return config


# =============================================================================
# PRESET CONFIGS (for backward compatibility)
# =============================================================================

# Long output for writers (no temperature!)
LONG_OUTPUT_CONFIG = gen_config(PROFILE_WRITER, max_output_tokens=32768)

# Critic config for reviewers (no temperature!)
CRITIC_CONFIG = gen_config(PROFILE_CRITIC, max_output_tokens=16384)

# Planner config for routing/planning
PLANNER_CONFIG = gen_config(PROFILE_PLANNER, max_output_tokens=8192)

# Research config for summarization
RESEARCH_CONFIG = gen_config(PROFILE_RESEARCH, max_output_tokens=16384)


# =============================================================================
# MODEL + CONFIG HELPER
# =============================================================================

def get_agent_config(profile: str) -> tuple[str, genai_types.GenerateContentConfig]:
    """
    Get both model and config for an agent profile.
    
    Args:
        profile: One of the PROFILE_* constants
        
    Returns:
        Tuple of (model_name, GenerateContentConfig)
    """
    model = pick_model(profile)
    
    # Profile-specific max tokens
    max_tokens = {
        PROFILE_PLANNER: 8192,
        PROFILE_RESEARCH: 16384,
        PROFILE_WRITER: 32768,
        PROFILE_CRITIC: 16384,
        PROFILE_VALIDATOR: 4096,
    }.get(profile, 8192)
    
    config = gen_config(profile, max_output_tokens=max_tokens)
    return model, config
