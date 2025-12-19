"""
Observability & Tracing Module.
Centralizes logging and state tracking for agents and tools.
"""

import datetime

def resolve_agent_name(ctx):
    """Aggressive resolution of agent name from any available context."""
    if not ctx: return "unknown"
    
    # Path 1: Direct agent attributes
    # ToolContext has 'agent_name'
    for attr in ["agent_name", "agent_id", "invoker_id", "invoker_name"]:
        name = getattr(ctx, attr, None)
        if name: return name

    agent_obj = getattr(ctx, "agent", None)
    if agent_obj:
        name = getattr(agent_obj, "name", None) or getattr(agent_obj, "id", None)
        if name: return name
    
    # Path 2: Invocation context (for tools/callbacks)
    ic = getattr(ctx, "invocation_context", None)
    if ic:
        # Check ic.agent_id (ADK 0.1.0+)
        name = getattr(ic, "agent_id", None) or getattr(ic, "agent_name", None)
        if name: return name
        
        # Check ic.agent object
        agent_obj = getattr(ic, "agent", None)
        if agent_obj:
            name = getattr(agent_obj, "name", None) or getattr(agent_obj, "id", None)
            if name: return name
            
    # Path 3: Session State (Active Agent fallback)
    session = getattr(ctx, "session", None)
    if not session and ic: session = getattr(ic, "session", None)
    
    # For ToolContext, state is available directly
    state = getattr(ctx, "state", None)
    if not state and session and hasattr(session, "state"):
        state = session.state

    if state:
        name = state.get("active_agent")
        if name: return name
    
    return "unknown"

def append_tool_trace(ctx, tool_call, tool_output):
    """
    Appends tool execution trace to Session State.
    Used by QA checks to verify evidence.
    """
    # Resolve session safely
    session = getattr(ctx, "session", None)
    ic = getattr(ctx, "invocation_context", None)
    
    if not session and ic:
        session = getattr(ic, "session", None)
    
    # Final fallback: check for session on context attributes
    if not session:
        for attr in ["_session", "session_id"]:
             val = getattr(ctx, attr, None)
             if val: # if it's just an id, we can't write to it easily here
                 break

    # Writing to state
    state = getattr(ctx, "state", None)
    if not state and session and hasattr(session, "state"):
        state = session.state

    if state is None:
        # print("DEBUG: No state found to write trace")
        return
        
    traces = state.get("tool_traces", [])
    if not isinstance(traces, list): traces = []
    
    agent_name = resolve_agent_name(ctx)
    tool_name = "unknown"
    if hasattr(tool_call, "function_call") and tool_call.function_call:
        tool_name = tool_call.function_call.name
    elif hasattr(tool_call, "name"):
        tool_name = tool_call.name
    
    trace_entry = {
        "agent": agent_name,
        "tool": tool_name,
        "ok": True, 
        "out_len": len(str(tool_output)),
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    traces.append(trace_entry)
    state["tool_traces"] = traces # Persist back to the dict
    
    # If we have a session object, ensure it's synced
    if session and hasattr(session, "state") and session.state is not state:
        session.state["tool_traces"] = traces

def append_security_event(ctx, event_type, details):
    """Logs security violations to Session State."""
    # Resolve session safely
    session = getattr(ctx, "session", None)
    ic = getattr(ctx, "invocation_context", None)
    if not session and ic:
        session = getattr(ic, "session", None)

    # Writing to state
    state = getattr(ctx, "state", None)
    if not state and session and hasattr(session, "state"):
        state = session.state

    if state is None:
        return
    
    events = state.get("security_events", [])
    if not isinstance(events, list): events = []
    
    agent_name = resolve_agent_name(ctx)
    
    events.append({
        "type": event_type,
        "agent": agent_name,
        "timestamp": datetime.datetime.now().isoformat(),
        **details
    })
    state["security_events"] = events
    
    if session and hasattr(session, "state") and session.state is not state:
        session.state["security_events"] = events

async def log_tool_trace(context=None, tool_call=None, tool_output=None, **kwargs):
    """
    Standard callback for logging tool usage.
    """
    try:
        ctx = context or kwargs.get('callback_context') or kwargs.get('context') or kwargs.get('invocation_context') or kwargs.get('tool_context')
        tc = tool_call or kwargs.get('tool_call') or kwargs.get('tool')
        out = tool_output or kwargs.get('tool_output') or kwargs.get('output') or kwargs.get('tool_response')
        
        if not ctx or not tc:
            # print(f"SKIP TRACE: Missing context or tool_call")
            return

        # Write to State for QA
        append_tool_trace(ctx, tc, out)
        
        # Resolve agent name
        agent_name = resolve_agent_name(ctx)
        
        tool_name = "unknown"
        if hasattr(tc, "function_call") and tc.function_call:
            tool_name = tc.function_call.name
        elif hasattr(tc, "name"):
            tool_name = tc.name
        
        print(f" [TRACE] '{agent_name}' -> '{tool_name}' (ok=True)")
        
    except Exception as e:
        print(f"Observability Error: {e}")
