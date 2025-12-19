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
