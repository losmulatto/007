# Copyright 2025 Google LLC - Adapted for Samha
"""
Deep Search Module - Iterative Research with HITL

Adapted from Google ADK Samples deep-search agent.
Provides comprehensive research with:
- Plan generation and approval (Human-in-the-Loop)
- Iterative search with quality evaluation
- Citation-rich report generation
"""
import datetime
import logging
import re
import urllib.parse
from typing import AsyncGenerator, Literal

from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from app.contracts_loader import load_contract
from app.model_router import attach_model_router
from app.web_search import search_web, search_news
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.planners import BuiltInPlanner
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types
from pydantic import BaseModel, Field

DUMMY_THOUGHT_SIGNATURE = b"samha_thought_signature"


def _domain_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc
    except Exception:
        return url


def _extract_sources_from_text(text: str) -> list[dict]:
    if not text:
        return []
    lines = text.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if re.search(r"keskeiset\\s+lähteet", line, re.IGNORECASE):
            start_idx = idx
            break
    if start_idx is None:
        return []

    sources = []
    for line in lines[start_idx + 1:]:
        if re.match(r"^\\s*#+\\s+", line):
            break
        if not line.strip():
            continue
        match = re.match(r"^\\s*(?:\\d+\\.|[-*])\\s+(.*)$", line)
        if not match:
            continue
        entry = match.group(1).strip()
        entry = re.sub(r"\\*\\*(.*?)\\*\\*", r"\\1", entry)
        entry = re.sub(r"`([^`]+)`", r"\\1", entry)
        url_match = re.search(r"https?://\\S+", entry)
        url = None
        if url_match:
            url = url_match.group(0).rstrip(").,;")
            entry = entry.replace(url_match.group(0), "").strip(" -–:;")
        title = entry.strip()
        if not title and url:
            title = url
        if title:
            sources.append({"title": title, "url": url})
    return sources


def _ensure_sources_from_state(state: dict) -> dict:
    sources = state.get("sources")
    if isinstance(sources, dict) and sources:
        return sources
    candidates = [
        state.get("section_research_findings", ""),
        state.get("final_cited_report", ""),
        state.get("report_sections", ""),
    ]
    inferred = []
    for text in candidates:
        inferred = _extract_sources_from_text(text)
        if inferred:
            break
    if not inferred:
        state["sources"] = {}
        return {}

    sources = {}
    for idx, item in enumerate(inferred, 1):
        short_id = f"src-{idx}"
        url = item.get("url")
        if not url:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(
                item["title"]
            )
        sources[short_id] = {
            "short_id": short_id,
            "title": item["title"],
            "url": url,
            "domain": _domain_from_url(url),
            "supported_claims": [],
        }
    state["sources"] = sources
    return sources


def _attach_router(agent: BaseAgent) -> BaseAgent:
    attach_model_router(agent)
    return agent


# =============================================================================
# CONFIGURATION
# =============================================================================

# Model settings - will be overridden by agent.py imports
import os
WORKER_MODEL = "gemini-3-flash-preview"
CRITIC_MODEL = "gemini-3-pro-preview"
MAX_SEARCH_ITERATIONS = int(os.environ.get("DEEP_SEARCH_ITERATIONS", 3))

from google.genai.types import ThinkingConfig
PLANNER_THINKING_CONFIG = ThinkingConfig(include_thoughts=True)


# =============================================================================
# STRUCTURED OUTPUT MODELS
# =============================================================================

class SearchQuery(BaseModel):
    """Model representing a specific search query for web search."""
    search_query: str = Field(
        description="A highly specific and targeted query for web search."
    )


class Feedback(BaseModel):
    """Model for providing evaluation feedback on research quality."""
    grade: Literal["pass", "fail"] = Field(
        description="Evaluation result. 'pass' if the research is sufficient, 'fail' if it needs revision."
    )
    comment: str = Field(
        description="Detailed explanation of the evaluation, highlighting strengths and/or weaknesses of the research."
    )
    follow_up_queries: list[SearchQuery] | None = Field(
        default=None,
        description="A list of specific, targeted follow-up search queries needed to fix research gaps. This should be null or empty if the grade is 'pass'.",
    )


# =============================================================================
# CALLBACKS
# =============================================================================

def collect_research_sources_callback(callback_context: CallbackContext) -> None:
    """Collects and organizes web-based research sources and their supported claims from agent events."""
    session = callback_context._invocation_context.session
    url_to_short_id = callback_context.state.get("url_to_short_id", {})
    sources = callback_context.state.get("sources", {})
    id_counter = len(url_to_short_id) + 1
    
    for event in session.events:
        if not (event.grounding_metadata and event.grounding_metadata.grounding_chunks):
            continue
        chunks_info = {}
        for idx, chunk in enumerate(event.grounding_metadata.grounding_chunks):
            if not chunk.web:
                continue
            url = chunk.web.uri
            title = (
                chunk.web.title
                if chunk.web.title != chunk.web.domain
                else chunk.web.domain
            )
            if url not in url_to_short_id:
                short_id = f"src-{id_counter}"
                url_to_short_id[url] = short_id
                sources[short_id] = {
                    "short_id": short_id,
                    "title": title,
                    "url": url,
                    "domain": chunk.web.domain,
                    "supported_claims": [],
                }
                id_counter += 1
            chunks_info[idx] = url_to_short_id[url]
        if event.grounding_metadata.grounding_supports:
            for support in event.grounding_metadata.grounding_supports:
                confidence_scores = support.confidence_scores or []
                chunk_indices = support.grounding_chunk_indices or []
                for i, chunk_idx in enumerate(chunk_indices):
                    if chunk_idx in chunks_info:
                        short_id = chunks_info[chunk_idx]
                        confidence = (
                            confidence_scores[i] if i < len(confidence_scores) else 0.5
                        )
                        text_segment = support.segment.text if support.segment else ""
                        sources[short_id]["supported_claims"].append(
                            {
                                "text_segment": text_segment,
                                "confidence": confidence,
                            }
                        )
    callback_context.state["url_to_short_id"] = url_to_short_id
    callback_context.state["sources"] = sources


def ensure_thought_signatures(callback_context: CallbackContext, llm_request) -> None:
    for content in llm_request.contents or []:
        parts = getattr(content, "parts", None) or []
        for part in parts:
            if getattr(part, "function_call", None) and not getattr(
                part, "thought_signature", None
            ):
                part.thought_signature = DUMMY_THOUGHT_SIGNATURE


def collect_sources_from_tool_callback(tool, args, tool_context, tool_response):
    tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    if tool_name not in ("search_web", "search_news", "search_verified_sources", "google_search"):
        return None

    text = tool_response
    if isinstance(text, dict):
        for key in ("result", "content", "output", "text"):
            nested = text.get(key)
            if nested:
                text = nested
                break
    if not text:
        return None

    sources = tool_context.state.get("sources", {})
    url_to_short_id = tool_context.state.get("url_to_short_id", {})
    if not isinstance(sources, dict):
        sources = {}
    if not isinstance(url_to_short_id, dict):
        url_to_short_id = {}
    id_counter = len(url_to_short_id) + 1

    added = 0
    # Try to extract sources from the tool output string
    # Importing it here to avoid circular dependencies if any
    try:
        from app.deep_search import _extract_sources_from_search_output
        extracted = _extract_sources_from_search_output(str(text))
    except ImportError:
        extracted = []

    for item in extracted:
        url = item.get("url")
        if not url:
            continue
        if url not in url_to_short_id:
            short_id = f"src-{id_counter}"
            url_to_short_id[url] = short_id
            sources[short_id] = {
                "short_id": short_id,
                "title": item.get("title") or _domain_from_url(url),
                "url": url,
                "domain": _domain_from_url(url),
                "supported_claims": [],
            }
            id_counter += 1
            added += 1

    tool_context.state["url_to_short_id"] = url_to_short_id
    tool_context.state["sources"] = sources
    if added:
        logging.info(f"[source-callback] added {added} sources, total {len(sources)}")
    return None


def citation_replacement_callback(
    callback_context: CallbackContext,
) -> genai_types.Content:
    """Replaces citation tags in a report with Markdown-formatted links."""
    final_report = callback_context.state.get("final_cited_report", "")
    sources = _ensure_sources_from_state(callback_context.state)

    def tag_replacer(match: re.Match) -> str:
        short_id = match.group(1)
        source_info = sources.get(short_id) if isinstance(sources, dict) else None
        if not source_info:
            logging.warning(f"Invalid citation tag found: {match.group(0)}")
            return f" [Lähde {short_id}]"
        display_text = source_info.get("title", source_info.get("domain", short_id))
        url = source_info.get("url")
        if url:
            return f" [{display_text}]({url})"
        return f" [{display_text}]"

    processed_report = re.sub(
        r'<cite\s+source\s*=\s*["\']?\s*(src-\d+)\s*["\']?\s*/>',
        tag_replacer,
        final_report,
    )
    processed_report = re.sub(r"\s+([.,;:])", r"\1", processed_report)
    callback_context.state["final_report_with_citations"] = processed_report
    return genai_types.Content(parts=[genai_types.Part(text=processed_report)])


def seed_sources_before_report(callback_context: CallbackContext, llm_request) -> None:
    """Populate sources before report composition so citations can be generated."""
    collect_research_sources_callback(callback_context)


# =============================================================================
# CUSTOM AGENT: LOOP CONTROL
# =============================================================================

class EscalationChecker(BaseAgent):
    """Checks research evaluation and escalates to stop the loop if grade is 'pass'."""

    def __init__(self, name: str):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        evaluation_result = ctx.session.state.get("research_evaluation")
        
        # Determine the grade safely (handle both dict and Pydantic model)
        grade = None
        if evaluation_result:
            if isinstance(evaluation_result, dict):
                grade = evaluation_result.get("grade")
            elif hasattr(evaluation_result, "grade"):
                grade = evaluation_result.grade
                
        logging.info(f"[{self.name}] Evaluation check: grade={grade}")
        print(f"[{self.name}] Evaluation check: grade={grade}")
        
        if grade == "pass":
            logging.info(
                f"[{self.name}] Research evaluation passed. Escalating to stop loop."
            )
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            reason = "failed" if evaluation_result else "not found"
            logging.info(
                f"[{self.name}] Research evaluation {reason}. Loop will continue."
            )
            print(f"[{self.name}] Research evaluation {reason}. Loop will continue.")
            yield Event(author=self.name)


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

plan_generator = LlmAgent(
    model=WORKER_MODEL,
    name="plan_generator",
    description="Generates or refines a 5-line action-oriented research plan.",
    instruction=f"""
You are a research strategist. Your job is to create a high-level RESEARCH PLAN, not a summary.
OUTPUT LANGUAGE: FINNISH.

If there is already a RESEARCH PLAN in the session state, improve upon it based on the user feedback.

RESEARCH PLAN (SO FAR):
{{{{ research_plan? }}}}

**TEHTÄVIEN LUOKITTELU**
Jokaisen kohdan tulee alkaa tehtävätyypillä:
- **`[RESEARCH]`**: Tiedonkeruu, tutkimus, analyysi (vaatii hakua)
- **`[DELIVERABLE]`**: Tiedon koonti, tuotokset (ei vaadi hakua)

**Vastausmuoto**
Tuota 5-kohtainen tutkimussuunnitelma:
- 5 tavoitetta luokiteltuna `[RESEARCH]`
- Mahdolliset välituotokset (`[DELIVERABLE]`)

**SÄÄNNÖT**
- Tavoitteesi on luoda laadukas suunnitelma ILMAN hakua
- Käytä selkeää suomen kieltä
- Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    tools=[search_web, search_news],
    output_key="research_plan",
)


section_planner = LlmAgent(
    model=WORKER_MODEL,
    name="section_planner",
    description="Creates a detailed markdown outline for a research report based on the approved plan.",
    instruction="""
You are a senior editor creating a report outline.

RESEARCH PLAN:
{research_plan}

**OUTPUT FORMAT**
Create a markdown outline for the final report using the structure below:

```markdown
# [Report Title]
## Introduction
## [Section based on RESEARCH goal 1]
## [Section based on RESEARCH goal 2]
## [Section based on RESEARCH goal 3]
...
## Conclusion
```

**RULES**
- One section per `[RESEARCH]` goal
- Sections should flow logically
- DO NOT perform any searches
""",
    output_key="report_sections",
)


section_researcher = LlmAgent(
    model=WORKER_MODEL,
    name="section_researcher",
    description="Executes the research plan using web search and documents findings.",
    planner=BuiltInPlanner(thinking_config=PLANNER_THINKING_CONFIG) if os.getenv("SAMHA_LLM_PROVIDER", "google") == "google" else None,
    before_model_callback=ensure_thought_signatures,
    instruction=f"""
You are a research specialist executing a detailed research plan.
OUTPUT LANGUAGE: FINNISH.

RESEARCH PLAN:
{{{{ research_plan }}}}

**YOUR DIRECTIVE**
Execute ALL `[RESEARCH]` goals systematically using `search_web`.

**PHASE 1: RESEARCH**
For each `[RESEARCH]` goal:
1. Use `search_web` tool to find relevant information
2. Synthesize findings into a concise summary
3. Include key facts, data, and quotes
4. Note sources for later citation

**PHASE 2: DELIVERABLES**
After ALL research is complete, execute `[DELIVERABLE]` goals using ONLY gathered summaries.

**RULES**
- Be thorough and systematic
- Include specific data and quotes
- Note source URLs
- Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
    tools=[search_web, search_news],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
    after_tool_callback=collect_sources_from_tool_callback,
)


research_evaluator = LlmAgent(
    model=CRITIC_MODEL,
    name="research_evaluator",
    description="Critically evaluates research and generates follow-up queries.",
    instruction=f"""
You are a meticulous quality assurance analyst evaluating the research findings in 'section_research_findings'.

**CRITICAL RULES**
1. Assume the given research topic is correct. Do not question the subject itself.
2. Your ONLY job is to assess quality, depth, and completeness of the research.
3. Evaluate: Comprehensiveness, logical flow, credible sources, depth of analysis, clarity.
4. Do NOT fact-check or question the fundamental premise.

**GRADING**
- "pass": Research thoroughly covers the topic
- "fail": Significant gaps in depth or coverage

If "fail": Write detailed comment about what's missing and generate 5-7 specific follow-up queries.

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
Your response must be a single, raw JSON object validating against the 'Feedback' schema.
""",
    output_schema=Feedback,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    output_key="research_evaluation",
)


enhanced_search_executor = LlmAgent(
    model=WORKER_MODEL,
    name="enhanced_search_executor",
    description="Executes follow-up searches and integrates new findings.",
    planner=BuiltInPlanner(thinking_config=PLANNER_THINKING_CONFIG) if os.getenv("SAMHA_LLM_PROVIDER", "google") == "google" else None,
    before_model_callback=ensure_thought_signatures,
    instruction="""
You are a specialist researcher executing a refinement pass.
OUTPUT LANGUAGE: FINNISH.
You have been activated because the previous research was graded as 'fail'.

1. Review the 'research_evaluation' state key to understand the feedback and required fixes.
2. Execute EVERY query listed in 'follow_up_queries' using the 'search_web' tool.
3. Synthesize the new findings and COMBINE them with existing information in 'section_research_findings'.
4. Your output MUST be the new, complete, and improved set of research findings.
""",
    tools=[search_web, search_news],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
    after_tool_callback=collect_sources_from_tool_callback,
)


report_composer = LlmAgent(
    model=CRITIC_MODEL,
    name="report_composer_with_citations",
    include_contents="none",
    description="Transforms research data and a markdown outline into a final, cited report.",
    before_model_callback=seed_sources_before_report,
    instruction="""
Transform the provided data into a polished, professional, and meticulously cited research report.
OUTPUT LANGUAGE: FINNISH.

---
### INPUT DATA
* Research Plan: `{research_plan}`
* Research Findings: `{section_research_findings}`
* Citation Sources: `{sources}`
* Report Structure: `{report_sections}`

---
### CRITICAL: Citation System
To cite a source, you MUST insert a special citation tag directly after the claim it supports.

**The only correct format is:** `<cite source="src-ID_NUMBER" />`

---
### Final Instructions
Generate a comprehensive report using ONLY the `<cite source="src-ID_NUMBER" />` tag system for all citations.
The final report must strictly follow the structure provided in the **Report Structure** markdown outline.
Do not include a "References" or "Sources" section; all citations must be in-line.
""",
    output_key="final_cited_report",
    after_agent_callback=citation_replacement_callback,
)


# =============================================================================
# ASSEMBLED PIPELINES
# =============================================================================

def get_research_pipeline():
    # Instantiate fresh agents for each pipeline to avoid parent assignment conflicts
    
    local_section_planner = _attach_router(LlmAgent(
        model=WORKER_MODEL,
        name="section_planner",
        description="Creates a detailed markdown outline for a research report based on the approved plan.",
        instruction="""
You are a senior editor creating a report outline.
OUTPUT LANGUAGE: FINNISH.

RESEARCH PLAN:
{research_plan}

**OUTPUT FORMAT**
Create a markdown outline for the final report using the structure below:

```markdown
# [Report Title]
## Introduction
## [Section based on RESEARCH goal 1]
## [Section based on RESEARCH goal 2]
## [Section based on RESEARCH goal 3]
...
## Conclusion
```

**RULES**
- One section per `[RESEARCH]` goal
- Sections should flow logically
- DO NOT perform any searches
""",
        output_key="report_sections",
    ))

    local_section_researcher = _attach_router(LlmAgent(
        model=WORKER_MODEL,
        name="section_researcher",
        description="Executes the research plan using web search and documents findings.",
        planner=BuiltInPlanner(thinking_config=PLANNER_THINKING_CONFIG) if os.getenv("SAMHA_LLM_PROVIDER", "google") == "google" else None,
        before_model_callback=ensure_thought_signatures,
        instruction=f"""
You are a research specialist executing a detailed research plan.
OUTPUT LANGUAGE: FINNISH.

RESEARCH PLAN:
{{{{ research_plan }}}}

**YOUR DIRECTIVE**
Execute ALL `[RESEARCH]` goals systematically using `search_web`.

**PHASE 1: RESEARCH**
For each `[RESEARCH]` goal:
1. Use `search_web` tool to find relevant information
2. Synthesize findings into a concise summary
3. Include key facts, data, and quotes
4. Note sources for later citation

**PHASE 2: DELIVERABLES**
After ALL research is complete, execute `[DELIVERABLE]` goals using ONLY gathered summaries.

**RULES**
- Be thorough and systematic
- Include specific data and quotes
- Note source URLs
- Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
        tools=[search_web, search_news],
        output_key="section_research_findings",
        after_agent_callback=collect_research_sources_callback,
        after_tool_callback=collect_sources_from_tool_callback,
    ))

    local_research_evaluator = _attach_router(LlmAgent(
        model=CRITIC_MODEL,
        name="research_evaluator",
        description="Critically evaluates research and generates follow-up queries.",
        instruction=f"""
You are a meticulous quality assurance analyst evaluating the research findings in 'section_research_findings'.
OUTPUT LANGUAGE: FINNISH.

**CRITICAL RULES**
1. Assume the given research topic is correct. Do not question the subject itself.
2. Your ONLY job is to assess quality, depth, and completeness of the research.
3. Evaluate: Comprehensiveness, logical flow, credible sources, depth of analysis, clarity.
4. Do NOT fact-check or question the fundamental premise.

**GRADING**
- "pass": Research thoroughly covers the topic
- "fail": Significant gaps in depth or coverage

If "fail": Write detailed comment about what's missing and generate 5-7 specific follow-up queries.

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
Your response must be a single, raw JSON object validating against the 'Feedback' schema.
""",
        output_schema=Feedback,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        output_key="research_evaluation",
    ))

    local_search_executor = _attach_router(LlmAgent(
        model=WORKER_MODEL,
        name="enhanced_search_executor",
        description="Executes follow-up searches and integrates new findings.",
        planner=BuiltInPlanner(thinking_config=PLANNER_THINKING_CONFIG) if os.getenv("SAMHA_LLM_PROVIDER", "google") == "google" else None,
        before_model_callback=ensure_thought_signatures,
        instruction="""
You are a specialist researcher executing a refinement pass.
OUTPUT LANGUAGE: FINNISH.
You have been activated because the previous research was graded as 'fail'.

1. Review the 'research_evaluation' state key to understand the feedback and required fixes.
2. Execute EVERY query listed in 'follow_up_queries' using the 'search_web' tool.
3. Synthesize the new findings and COMBINE them with existing information in 'section_research_findings'.
4. Your output MUST be the new, complete, and improved set of research findings.
""",
        tools=[search_web, search_news],
        output_key="section_research_findings",
        after_agent_callback=collect_research_sources_callback,
        after_tool_callback=collect_sources_from_tool_callback,
    ))

    local_report_composer = _attach_router(LlmAgent(
        model=CRITIC_MODEL,
        name="report_composer_with_citations",
        include_contents="none",
        description="Transforms research data and a markdown outline into a final, cited report.",
        before_model_callback=seed_sources_before_report,
        instruction="""
Transform the provided data into a polished, professional, and meticulously cited research report.
OUTPUT LANGUAGE: FINNISH.

---
### INPUT DATA
* Research Plan: `{research_plan}`
* Research Findings: `{section_research_findings}`
* Citation Sources: `{sources}`
* Report Structure: `{report_sections}`

---
### CRITICAL: Citation System
To cite a source, you MUST insert a special citation tag directly after the claim it supports.

**The only correct format is:** `<cite source="src-ID_NUMBER" />`

---
### Final Instructions
Generate a comprehensive report using ONLY the `<cite source="src-ID_NUMBER" />` tag system for all citations.
The final report must strictly follow the structure provided in the **Report Structure** markdown outline.
Do not include a "References" or "Sources" section; all citations must be in-line.
""",
        output_key="final_cited_report",
        after_agent_callback=citation_replacement_callback,
    ))

    return SequentialAgent(
        name="research_pipeline",
        description="Executes a pre-approved research plan. It performs iterative research, evaluation, and composes a final, cited report.",
        sub_agents=[
            local_section_planner,
            local_section_researcher,
            LoopAgent(
                name="iterative_refinement_loop",
                max_iterations=MAX_SEARCH_ITERATIONS,
                sub_agents=[
                    local_research_evaluator,
                    EscalationChecker(name="escalation_checker"),
                    local_search_executor,
                ],
            ),
            local_report_composer,
        ],
    )


def get_syvahaku_agent(suffix: str = "") -> LlmAgent:
    """Returns a fresh instance of the syvahaku agent."""
    return _attach_router(LlmAgent(
        name=f"syvahaku{suffix}",
        model=WORKER_MODEL,
        description="Syvällinen tutkimusagentti. Luo monivaiheisen tutkimussuunnitelman, kerää tietoa iteratiivisesti, arvioi laatua, ja tuottaa kattavan raportin lähdeviittein.",
        instruction=f"""
## SINUN ROOLISI: SYVÄHAKU (DEEP RESEARCH)
{load_contract("syvahaku")}

Olet Samhan syvällisen tutkimuksen asiantuntija. Teet perusteellista tutkimusta käyttäen iteratiivista prosessia.

### PROSESSI

1. **SUUNNITTELU**: Käytä `plan_generator` -työkalua luodaksesi tutkimussuunnitelman
2. **HYVÄKSYNTÄ**: Esitä suunnitelma käyttäjälle ja pyydä hyväksyntä
3. **TOTEUTUS**: Kun käyttäjä hyväksyy (esim. "ok", "hyväksyn", "aloita"), delegoi `research_pipeline` -agentille

### MILLOIN KÄYTETÄÄN

Käytä syvähakua kun:
- Käyttäjä pyytää perusteellista tutkimusta
- Tarvitaan useita lähteitä ja lähdekritiikkiä
- Halutaan kattava raportti viitteineen
- Aihe on monimutkainen ja vaatii iteraatiota

### ESIMERKKIPYYNNÖT

- "Tutki kattavasti nuorten mielenterveyden tilannetta Suomessa"
- "Tee syvällinen analyysi EU:n antirasismipolitiikasta"
- "Kerää tutkimustietoa trauma-informoidusta työotteesta"

### TÄRKEÄÄ

- Älä vastaa suoraan, vaan luo AINA ensin tutkimussuunnitelma
- Odota käyttäjän hyväksyntää ennen tutkimuksen aloittamista
- Pysy iteratiivisessa prosessissa kunnes laatu on riittävä

Current date: {datetime.datetime.now().strftime("%Y-%m-%d")}
""",
        sub_agents=[get_research_pipeline()],
        tools=[AgentTool(plan_generator)],
        output_key="research_plan",
    ))

# Default instance with parent-clearing hack
syvahaku_agent = get_syvahaku_agent()

# Alias for easy import
root_agent = syvahaku_agent
