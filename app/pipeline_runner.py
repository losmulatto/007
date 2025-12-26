import asyncio
from app.egress import scrub_for_user

async def run_quality_pipeline(user_input, runner, session):
    """
    Runs the quality-hardened pipeline:
    Coordinator -> QA Policy -> QA Quality -> (Revision Loop) -> User
    """
    MAX_RETRIES = 1
    
    # Initial Run
    result = await runner.run_agent_async("koordinaattori", session, user_input)
    
    # Check QA Quality Result
    qa_result = session.state.get("qa_quality_result")
    
    # Revision Loop
    retries = 0
    while retries < MAX_RETRIES:
        if qa_result and qa_result.get("quality_decision") == "NEEDS_REVISION":
             print(f"🔄 REVISION LOOP TRIGGERED (Attempt {retries+1}/{MAX_RETRIES})")
             
             # Prepare feedback
             fix_list = qa_result.get("fix_list", [])
             rewrite_instr = qa_result.get("rewrite_instructions", "")
             feedback = (
                 f"QA_QUALITY REJECTED THE DRAFT.\n"
                 f"REASON: {rewrite_instr}\n"
                 f"REQUIRED FIXES: {fix_list}\n"
                 f"ACTION: Revise the content immediately."
             )
             
             # Inject feedback into next turn
             # We re-run Coordinator with feedback
             await runner.run_agent_async("koordinaattori", session, feedback)
             
             # Re-check QA result (Coordinator delegates to QA again)
             qa_result = session.state.get("qa_quality_result")
             retries += 1
        else:
            break
            
    # Final Egress Scrub
    final_text = session.state.get("draft_response", "")
    scrubbed_text = scrub_for_user(final_text)
    
    return scrubbed_text
