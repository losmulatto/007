import os
from typing import Optional

from google.adk.models.lite_llm import LiteLlm

from app.env import load_env

load_env()


_DEFAULT_PROVIDER = os.getenv("SAMHA_LLM_PROVIDER", "google")
_DEFAULT_GOOGLE_BASE = os.getenv("SAMHA_GOOGLE_LLM", "gemini-3-flash-preview")
_DEFAULT_GOOGLE_PRO = os.getenv("SAMHA_GOOGLE_LLM_PRO", "gemini-3-flash-preview")


_DEFAULT_OPENAI_BASE = os.getenv("SAMHA_OPENAI_LLM", "openai/gpt-4o-mini")
_DEFAULT_OPENAI_PRO = os.getenv("SAMHA_OPENAI_LLM_PRO", "openai/gpt-4o")
_DEFAULT_OPENAI_MAX_OUTPUT = int(
    os.getenv("SAMHA_OPENAI_MAX_OUTPUT_TOKENS", "8192")
)
_DEFAULT_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_DEFAULT_OPENAI_API_BASE = (
    os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
)

# DeepSeek Direct API configuration
_DEFAULT_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
_DEFAULT_DEEPSEEK_MODEL = os.getenv("SAMHA_DEEPSEEK_MODEL", "deepseek-chat")
_DEFAULT_DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
_DEFAULT_DEEPSEEK_MAX_OUTPUT = int(os.getenv("SAMHA_DEEPSEEK_MAX_OUTPUT_TOKENS", "8192"))

# Claude (Anthropic) API configuration
_DEFAULT_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_DEFAULT_CLAUDE_MODEL = os.getenv("SAMHA_CLAUDE_MODEL", "claude-opus-4-5")
_DEFAULT_CLAUDE_WORKER_MODEL = os.getenv("SAMHA_CLAUDE_WORKER_MODEL", "claude-haiku-4-5")
_DEFAULT_CLAUDE_PLANNER_MODEL = os.getenv("SAMHA_CLAUDE_PLANNER_MODEL", "claude-opus-4-5")

_DEFAULT_CLAUDE_MAX_OUTPUT = int(os.getenv("SAMHA_CLAUDE_MAX_OUTPUT_TOKENS", "8192"))

# Agent names that should use the lighter "worker" model (Haiku)
# These are simple validators, checkers, and preprocessors
_CLAUDE_WORKER_AGENTS = {
    "samha_context_checker",
    "section_validator", 
    "source_validator",
    "format_checker",
    "data_validator",
    "context_validator",
    "quality_checker",
}


# Lazy import for DeepSeek Reasoner to avoid circular imports
_deepseek_reasoner_instance = None


def _get_deepseek_reasoner():
    """Lazy initialization of DeepSeek Reasoner LLM."""
    global _deepseek_reasoner_instance
    if _deepseek_reasoner_instance is None:
        from app.deepseek_reasoner import DeepSeekReasonerLlm
        _deepseek_reasoner_instance = DeepSeekReasonerLlm(
            model="deepseek-reasoner",
            api_key=_DEFAULT_DEEPSEEK_API_KEY,
            api_base=_DEFAULT_DEEPSEEK_API_BASE,
            max_tokens=_DEFAULT_DEEPSEEK_MAX_OUTPUT,
            enable_thinking=True,
        )
    return _deepseek_reasoner_instance


def _normalize_provider(value: Optional[str]) -> str:
    if not value:
        return "google"
    lowered = value.strip().lower()
    if lowered in {"openai", "open-ai", "oa"}:
        return "openai"
    if lowered in {"google", "gemini", "vertex"}:
        return "google"
    if lowered in {"deepseek", "ds"}:
        return "deepseek"
    if lowered in {"deepseek-reasoner", "ds-r", "reasoner"}:
        return "deepseek-reasoner"
    if lowered in {"claude", "anthropic", "opus"}:
        return "claude"
    return lowered


def _is_pro_model(model_name: Optional[str]) -> bool:
    if not model_name:
        return False
    # Handle cases where model_name might be a LiteLlm instance or other object
    if not isinstance(model_name, str):
        # Try to extract model string from LiteLlm or similar
        if hasattr(model_name, 'model'):
            model_str = model_name.model
            if callable(model_str):
                return False
            if isinstance(model_str, str):
                model_name = model_str
            else:
                return False
        elif hasattr(model_name, '_model'):
            model_name = model_name._model
        else:
            return False
    if not isinstance(model_name, str):
        return False
    lowered = model_name.lower()
    return "pro" in lowered or "critic" in lowered or "reasoner" in lowered


def _get_claude_model_for_agent(agent_name: Optional[str]) -> str:
    """Select Claude model based on agent type.
    
    Worker agents (validators, checkers) -> Haiku (50K tokens/min limit)
    Planner agents (writers, planners) -> Opus (30K tokens/min limit)
    """
    if not agent_name:
        return _DEFAULT_CLAUDE_PLANNER_MODEL  # Default to Opus for unknown agents
    
    agent_lower = agent_name.lower()
    
    # Check if this is a worker agent by name
    if agent_lower in _CLAUDE_WORKER_AGENTS:
        return _DEFAULT_CLAUDE_WORKER_MODEL
    
    # Also check for common worker patterns
    worker_patterns = ["checker", "validator", "context_", "format_"]
    for pattern in worker_patterns:
        if pattern in agent_lower:
            return _DEFAULT_CLAUDE_WORKER_MODEL
    
    # Default to planner (Opus) for important tasks
    return _DEFAULT_CLAUDE_PLANNER_MODEL


def _resolve_target_model(provider: str, is_pro: bool, agent_name: Optional[str] = None) -> str:
    if provider == "openai":
        return _DEFAULT_OPENAI_PRO if is_pro else _DEFAULT_OPENAI_BASE
    if provider == "deepseek":
        # Direct DeepSeek API - prefix with openai/ for LiteLLM routing
        # Use provider-specified model or default
        base_model = _DEFAULT_DEEPSEEK_MODEL or "deepseek-chat"
        # Normalize to openai/ prefix for LiteLLM if not present
        if not any(base_model.startswith(p) for p in ["openai/", "deepseek/"]):
            return f"openai/{base_model}"
        return base_model
    if provider == "deepseek-reasoner":
        # DeepSeek Reasoner (V3) as a general fallback to chat mode
        return "openai/deepseek-chat"
    if provider == "claude":
        # Claude - select model based on agent type (Haiku for workers, Opus for planners)
        claude_model = _get_claude_model_for_agent(agent_name)
        return f"anthropic/{claude_model}"
    return _DEFAULT_GOOGLE_PRO if is_pro else _DEFAULT_GOOGLE_BASE



def _clamp_output_tokens(llm_request, max_tokens: int) -> None:
    """Clamp output tokens for providers with limits."""
    if not llm_request or not llm_request.config or max_tokens <= 0:
        return
    current = llm_request.config.max_output_tokens
    if current and current > max_tokens:
        llm_request.config.max_output_tokens = max_tokens


def _fix_gemini_3_signatures(llm_request) -> None:
    """Inject mandatory thought signatures for Gemini 3 models.
    
    If signatures are missing or corrupted, use the 'dummy' signature 
    recommended in the Gemini 3 developer guide to bypass 400 errors.
    """
    if not llm_request or not llm_request.model or "gemini-3" not in llm_request.model:
        return
    
    print(f"[Gemini 3 Router] Fixing signatures for model: {llm_request.model}")
        
    DUMMY_SIGNATURE = "context_engineering_is_the_way_to_go"
    
    if not hasattr(llm_request, "contents") or not llm_request.contents:
        return
        
    # Add thinking level and temperature config (Gemini 3 MUST HAVE temp 1.0)
    if hasattr(llm_request, "config") and llm_request.config:
        # Force temperature to 1.0 as per developer guide
        llm_request.config.temperature = 1.0
        
        if not hasattr(llm_request.config, "thinking_config") or not llm_request.config.thinking_config:
            print(f"[Gemini 3 Router] Requesting model: {llm_request.model}")
            try:
                from google.genai import types
                
                # Re-enabling thinking for all Gemini 3 models as requested
                is_flash = "flash" in llm_request.model.lower()
                level = "minimal" if is_flash else "high"
                
                llm_request.config.thinking_config = types.ThinkingConfig(
                    thinking_level=level,
                    include_thoughts=False # Thoughts are handled by ADK internal stream if enabled
                )
                print(f"[Gemini 3 Router] Enabled {level} thinking for {'Flash' if is_flash else 'Pro'}.")
            except (ImportError, Exception) as e:
                print(f"[Gemini 3 Router] Error setting thinking_config: {e}")
                pass

    for content in llm_request.contents:
        if not hasattr(content, "parts") or not content.parts:
            continue
            
        for part in content.parts:
            # Check for function calls - they MUST have a signature in Gemini 3
            if hasattr(part, "function_call") and part.function_call:
                # If thought_signature is missing or empty, inject the bypass string
                if not hasattr(part, "thought_signature") or not part.thought_signature:
                    part.thought_signature = DUMMY_SIGNATURE
                    # Also try to set it in the dictionary if it's a raw part
                    if isinstance(part, dict):
                        part["thought_signature"] = DUMMY_SIGNATURE
            
            # Check for thinking parts
            if hasattr(part, "thought") and part.thought:
                if not hasattr(part, "thought_signature") or not part.thought_signature:
                    part.thought_signature = DUMMY_SIGNATURE
            
            # Universal fix: Ensure thought_signature is never empty in Gemini 3 turns
            if not getattr(part, "thought_signature", None) and (hasattr(part, "text") or hasattr(part, "function_call")):
                setattr(part, "thought_signature", DUMMY_SIGNATURE)

async def fix_gemini_3_response_callback(callback_context=None, llm_response=None, **kwargs):
    """Intercept empty Gemini 3 responses to prevent pipeline crashes.
    
    If the response is empty (but might contain signatures/thoughts),
    inject a placeholder string so the ADK parser doesn't throw.
    """
    ctx = callback_context or kwargs.get("callback_context") or kwargs.get("context")
    res = llm_response or kwargs.get("llm_response")
    if not res:
        return
        
    print(f"[Gemini 3 Router] POST-MODEL Callback triggered for {getattr(res, 'model', 'unknown')}")
    print(f"[Gemini 3 Router] Finish Reason: {getattr(res, 'finish_reason', 'unknown')}")
    
    # NEW: If the agent expects a structured output, we must NOT inject arbitrary text
    # as it will break the JSON parser/validator (Pydantic).
    # We check the flag we set in route_model_callback.
    agent_has_schema = False
    if ctx and hasattr(ctx, "state"):
        agent_has_schema = ctx.state.get("_agent_has_schema", False)
    
    # Check if we have any valid output
    has_text = False
    part_count = 0
    if hasattr(res, "content") and res.content and res.content.parts:
        part_count = len(res.content.parts)
        for i, part in enumerate(res.content.parts):
            # Log part details
            p_text = getattr(part, "text", None)
            p_call = getattr(part, "function_call", None)
            p_sig = getattr(part, "thought_signature", None)
            print(f"[Gemini 3 Router] Part {i}: text={bool(p_text)}, call={bool(p_call)}, thought={bool(p_sig)}")
            
            if p_text and len(p_text.strip()) > 0:
                has_text = True
                # No break here, we want to log all parts
            
    has_tools = hasattr(res, "tool_calls") and res.tool_calls
    
    print(f"[Gemini 3 Router] has_text: {has_text}, has_tools: {has_tools}, parts: {part_count}, schema: {bool(agent_has_schema)}")
    
    if not has_text and not has_tools:
        # Avoid infinite loops of empty responses
        count = 0
        if ctx and hasattr(ctx, "state"):
            count = ctx.state.get("_empty_injection_count", 0)
            ctx.state["_empty_injection_count"] = count + 1
            
        if count >= 3:
            print(f"[Gemini 3 Router] Stopping injection after {count} attempts.")
            return

        if agent_has_schema:
            print(f"[Gemini 3 Router] Skipping injection for SCHEMA-based agent.")
            return

        print(f"[Gemini 3 Router] Detected EMPTY response. Injecting placeholder ( ).")
        
        try:
            from google.genai import types
            
            # Injection logic
            if not res.content:
                res.content = types.Content(role="model", parts=[])
            
            # Use a slightly more substantial placeholder than just whitespace if needed, 
            # or stick to " " which UI now handles better.
            placeholder = " " 
            
            if not res.content.parts:
                res.content.parts = [types.Part(text=placeholder)]
            else:
                # Add text to existing parts (e.g. if they only have signatures)
                res.content.parts.append(types.Part(text=placeholder))
        except Exception as e:
            print(f"[Gemini 3 Router] Injection failed: {e}")
    else:
        # If it has text, log at least something
        if has_text:
            msg_text = "".join([p.text for p in res.content.parts if hasattr(p, 'text') and p.text])
            print(f"[Gemini 3 Router] Response received (len={len(msg_text)})")
        elif has_tools:
            print(f"[Gemini 3 Router] Tool calls received: {[t.function_call.name for t in res.tool_calls]}")

def _strip_unsupported_params(llm_request) -> None:
    """Remove parameters not supported by OpenAI-compatible APIs."""
    if not llm_request or not llm_request.config:
        return
    
    # 1. response_schema is Gemini-specific (causes 400 on OpenAI/Anthropic/DeepSeek)
    if hasattr(llm_request.config, "response_schema"):
        llm_request.config.response_schema = None
        
    # 2. response_mime_type is also Gemini-specific
    if hasattr(llm_request.config, 'response_mime_type'):
        llm_request.config.response_mime_type = None
        
    # 3. thinking_config is Gemini 3 specific
    if hasattr(llm_request.config, 'thinking_config'):
        llm_request.config.thinking_config = None


async def route_model_callback(callback_context=None, llm_request=None, **kwargs):
    ctx = callback_context or kwargs.get("callback_context") or kwargs.get("context")
    llm_request = llm_request or kwargs.get("llm_request")
    if not llm_request:
        return

    print(f"[Model Router] Routing request for agent: {getattr(llm_request, 'agent_name', 'unknown')}")

    provider_value = _DEFAULT_PROVIDER
    if ctx and hasattr(ctx, "session"):
        provider_value = ctx.session.state.get("llm_provider", provider_value)
    provider = _normalize_provider(provider_value)

    agent = None
    agent_name = None
    if ctx is not None:
        agent = getattr(getattr(ctx, "_invocation_context", None), "agent", None)
        if agent is not None:
            agent_name = getattr(agent, "name", None)

    current_model = llm_request.model or getattr(agent, "model", None)
    target_model = _resolve_target_model(provider, _is_pro_model(current_model), agent_name)
    
    # Log which Claude model is selected for debugging
    if provider == "claude" and agent_name:
        print(f"[Claude Router] Agent '{agent_name}' -> Model '{target_model}'")


    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or _DEFAULT_OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Set it to use the OpenAI provider."
            )
        if agent is not None:
            agent.model = LiteLlm(
                model=target_model,
                api_key=api_key,
                api_base=_DEFAULT_OPENAI_API_BASE,
            )
        _clamp_output_tokens(llm_request, _DEFAULT_OPENAI_MAX_OUTPUT)
        _strip_unsupported_params(llm_request)

    elif provider == "deepseek":
        api_key = _DEFAULT_DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Get one at https://platform.deepseek.com"
            )
        if agent is not None:
            agent.model = LiteLlm(
                model=target_model,
                api_key=api_key,
                api_base=_DEFAULT_DEEPSEEK_API_BASE,
                custom_llm_provider="openai",
            )
        _clamp_output_tokens(llm_request, _DEFAULT_DEEPSEEK_MAX_OUTPUT)
        _strip_unsupported_params(llm_request)

    elif provider == "deepseek-reasoner":
        # NOTE: DeepSeek Reasoner (thinking mode) is not compatible with ADK
        # because it requires reasoning_content passthrough between API calls.
        # Using deepseek-chat (V3.2) instead - it's DeepSeek's best production model.
        api_key = _DEFAULT_DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Get one at https://platform.deepseek.com"
            )
        # Use deepseek-chat via LiteLLM - fully compatible with ADK
        if agent is not None:
            agent.model = LiteLlm(
                model="openai/deepseek-chat",
                api_key=api_key,
                api_base=_DEFAULT_DEEPSEEK_API_BASE,
                custom_llm_provider="openai",
            )
        _clamp_output_tokens(llm_request, _DEFAULT_DEEPSEEK_MAX_OUTPUT)
        _strip_unsupported_params(llm_request)

    elif provider == "claude":
        api_key = _DEFAULT_ANTHROPIC_API_KEY
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Get one at https://console.anthropic.com/"
            )
        # Claude Opus 4.5 via LiteLLM with Anthropic provider
        if agent is not None:
            agent.model = LiteLlm(
                model=target_model,
                api_key=api_key,
            )
        _clamp_output_tokens(llm_request, _DEFAULT_CLAUDE_MAX_OUTPUT)
        _strip_unsupported_params(llm_request)

    llm_request.model = target_model
    if agent is not None:
        if hasattr(agent, "output_schema") and agent.output_schema:
            print(f"[Gemini 3 Router] Agent {agent.name} has output_schema. Flagging in state.")
            ctx.state["_agent_has_schema"] = True
        else:
            ctx.state["_agent_has_schema"] = False
            
        # Reset empty injection counter for this new turn/agent
        if ctx and hasattr(ctx, "state"):
            ctx.state["_empty_injection_count"] = 0
            
    _fix_gemini_3_signatures(llm_request)
    
    if agent is not None:
        if not hasattr(agent, "after_model_callback") or not agent.after_model_callback:
            agent.after_model_callback = fix_gemini_3_response_callback
        else:
            if isinstance(agent.after_model_callback, list):
                if fix_gemini_3_response_callback not in agent.after_model_callback:
                    agent.after_model_callback.append(fix_gemini_3_response_callback)
            elif agent.after_model_callback != fix_gemini_3_response_callback:
                agent.after_model_callback = [agent.after_model_callback, fix_gemini_3_response_callback]

    if agent is not None and provider not in ("deepseek-reasoner",) and not isinstance(agent.model, LiteLlm):
        agent.model = target_model



def attach_model_router(agent) -> None:
    if not agent or not hasattr(agent, "before_model_callback"):
        return
        
    # Guard: Don't attach twice
    if hasattr(agent, "_model_router_attached") and agent._model_router_attached:
        return

    existing = getattr(agent, "before_model_callback", None)
    if not existing:
        agent.before_model_callback = route_model_callback
    elif isinstance(existing, list):
        if route_model_callback not in existing:
             agent.before_model_callback = [route_model_callback, *existing]
    elif existing is not route_model_callback:
        agent.before_model_callback = [route_model_callback, existing]
    
    agent._model_router_attached = True


def attach_to_all_agents(root_agent) -> None:
    """Recursively attach the model router to an agent and all its sub-agents."""
    if not root_agent:
        return
        
    # Attach to this agent
    attach_model_router(root_agent)
    
    # Recurse into sub-agents if they exist
    if hasattr(root_agent, "sub_agents") and root_agent.sub_agents:
        for sub in root_agent.sub_agents:
            attach_to_all_agents(sub)
    
    # Also check if it's a workflow agent or has nested agents in other attributes
    # (ADK specific patterns)
