"""
Samha Middleware Layer

Deterministic hooks for safety and compliance.
"""

from app.pii_scrubber import pii_scrubber

def chain_callbacks(*callbacks):
    """
    Combines multiple async callbacks into a single function.
    Executes valid callbacks sequentially.
    """
    async def chained_callback(context=None, **kwargs):
        for callback in callbacks:
            if not callback:
                continue
            await callback(context=context, **kwargs)
    return chained_callback

async def pii_sanitize_middleware(context=None, **kwargs):
    """
    Middleware: Scans 'draft_response' in session state and removes PII 
    BEFORE the QA agent sees it (or before final output).
    """
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return

    try:
        session = getattr(ctx, 'session', None)
        if not session:
            return

        state = session.state
        draft = state.get("draft_response", "")

        if draft:
            cleaned_text, red_flags = pii_scrubber(draft)
            
            if red_flags:
                print(f"🔒 MWARE: Redacted PII from draft: {red_flags}")
                # Update the state with the sanitized version
                state["draft_response"] = cleaned_text
                
                # Also inject a notification into the instruction so the QA knows we scrubbed it
                # (Optional, but helps QA understand why there are [EMAIL_REDACTED] tags)
                if hasattr(ctx, 'instruction') and ctx.instruction:
                   ctx.instruction += f"\n\n[SYSTEM NOTE]: PII-middleware has redacted the following from the draft: {red_flags}."

    except Exception as e:
        print(f"Callback error (pii_middleware): {e}")

from app.quality_lint import lint_quality

async def quality_lint_middleware(context=None, **kwargs):
    """
    Middleware: Runs deterministic quality checks on 'draft_response'.
    If checks fail, injects specific failure notes into the QA agent's instructions.
    """
    ctx = context or kwargs.get('callback_context')
    if ctx is None: return

    try:
        session = getattr(ctx, 'session', None)
        if not session:
            return

        state = session.state
        draft = state.get("draft_response", "")
        
        if draft:
            result = lint_quality(draft)
            state["quality_lint"] = result
            
            if not result["passed"]:
                state["quality_lint_failed"] = True
                
                # Inject failure notice into instruction
                if hasattr(ctx, 'instruction') and ctx.instruction:
                    issues_str = "\n- ".join(result["issues"])
                    ctx.instruction += (
                        f"\n\n[SYSTEM ALERT]: Quality Lint Failed!\n"
                        f"The following issues were found in the draft:\n- {issues_str}\n"
                        f"You MUST output NEEDS_REVISION and list these fixes."
                    )
    except Exception as e:
        print(f"Callback error (quality_lint_middleware): {e}")
