from __future__ import annotations

import asyncio
import itertools
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import gradio as gr
import re
from agents import (
    Agent,
    Runner,
    trace,
    function_tool,
    gen_trace_id,
    input_guardrail,
    output_guardrail,
    GuardrailFunctionOutput,
)
from agents.model_settings import ModelSettings
from search_agent import search_agent, SearchSummary
from planner_agent import planner_agent
from writer_agent import writer_agent
from email_agent import email_agent
import html
from agents.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
)

# --------------------------------------------------------------------------------------
# Env
# --------------------------------------------------------------------------------------
load_dotenv(override=True)

# --------------------------------------------------------------------------------------
# Live status bus (for streaming status to the UI)
# --------------------------------------------------------------------------------------
class StatusBus:
    def __init__(self):
        self._q: asyncio.Queue[str] = asyncio.Queue()

    async def publish(self, msg: str):
        await self._q.put(msg)

    async def get(self, timeout: float = 0.25) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

STATUS_BUS = StatusBus()


@function_tool
async def search_once(query: str) -> Dict[str, Any]:
    """
    Run a single search via the search_agent and return {query, summary, sources}.
    Sequential search; manager loops as needed.
    """
    r = await Runner.run(search_agent, query)
    out = r.final_output_as(SearchSummary)
    return {"query": query, "summary": out.summary, "sources": out.sources}

# --------------------------------------------------------------------------------------
# Helper: extract raw user query for guardrails
# --------------------------------------------------------------------------------------
def _extract_query_only(message: str) -> str:
    if "QUERY:" in message:
        tail = message.split("QUERY:", 1)[-1]
        return tail.split("\n", 1)[0].strip()
    return message.strip()

# --------------------------------------------------------------------------------------
# Clarifier
# --------------------------------------------------------------------------------------
class ClarificationQuestions(BaseModel):
    q1: str = Field(description="First clarifying question")
    q2: str = Field(description="Second clarifying question")
    q3: str = Field(description="Third clarifying question")

CLARIFY_INSTRUCTIONS = (
    "You are a clarifier. Given a user query, ask exactly three concrete clarifying questions "
    "that would materially improve the quality of research and the final report. "
    "Avoid meta-questions; focus on scope, constraints, target audience, timeframe, and success criteria. "
    "Return only the questions."
)

clarifier_agent = Agent(
    name="ClarifierAgent",
    instructions=CLARIFY_INSTRUCTIONS,
    model="gpt-4o-mini",
    output_type=ClarificationQuestions,
)


@function_tool
def convert_to_html(markdown_text: str, doc_title: str | None = None) -> dict:
    """
    Convert basic Markdown to simple HTML (no external dependencies).
    Handles headings, bold, italics, links, lists, and paragraphs.
    Returns: {"html": "<!doctype html>..."}
    """
    title = html.escape(doc_title or "Report")
    text = html.escape(markdown_text)

    # --- very lightweight markdown replacements ---
    text = re.sub(r"^###### (.*)$", r"<h6>\1</h6>", text, flags=re.MULTILINE)
    text = re.sub(r"^##### (.*)$", r"<h5>\1</h5>", text, flags=re.MULTILINE)
    text = re.sub(r"^#### (.*)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.*)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)

    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"<a href='\2'>\1</a>", text)
    text = re.sub(r"^- (.*)$", r"<li>\1</li>", text, flags=re.MULTILINE)
    text = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", text, count=1)

    # simple paragraph wrapping
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    html_body = "".join(
        f"<p>{line}</p>" if not line.startswith("<h") and not line.startswith("<ul>") else line
        for line in lines
    )

    html_doc = (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "</head><body>"
        f"{html_body}"
        "</body></html>"
    )
    return {"html": html_doc}

# --------------------------------------------------------------------------------------
# Tools for the Manager (LLM-callable)
# --------------------------------------------------------------------------------------
@function_tool
async def yield_status(message: str) -> str:
    """Stream a short status update to the caller/UI."""
    print(message)
    await STATUS_BUS.publish(message + "\n")
    return message

# Expose agents as tools the manager can call
clarify_tool = clarifier_agent.as_tool(
    tool_name="clarify_with_llm",
    tool_description="Ask exactly three clarifying questions for the query."
)
plan_tool = planner_agent.as_tool(
    tool_name="plan_with_llm",
    tool_description="Propose exactly N web search items for the query."
)
write_tool = writer_agent.as_tool(
    tool_name="write_with_llm",
    tool_description="Generate a detailed markdown report from notes and the original query."
)
email_tool = email_agent.as_tool(
    tool_name="email_with_llm",
    tool_description="send a detailed HTML email with an appropriate subject line."
)

# --------------------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------------------
class SimpleGuardrailOutput(BaseModel):
    ok: bool = Field(default=True)
    flags: List[str] = Field(default_factory=list)
    brief: Optional[str] = Field(default=None)

INPUT_GUARDRAIL_INSTRUCTIONS = """
You are an input gate for a research system. Decide only whether the user query is safe and actionable.
Return JSON for SimpleGuardrailOutput.

Rules:
- Block: illegal/unsafe content, PII requests, adult-only content, or requests for private/live/inaccessible data.
- If vague/underspecified, set ok=true and add 'vague' in flags; use 'brief' to suggest 1–2 clarifications.
- If safe and specific enough to research, ok=true.
Keep 'brief' concise; no extra text beyond the JSON.
"""

OUTPUT_GUARDRAIL_INSTRUCTIONS = """
You are an output gate for research reports. Decide only whether the draft report is safe, factual-sounding, and properly structured.
Return JSON for SimpleGuardrailOutput.

Rules:
- Require: Executive summary, key findings, limitations, next steps (or equivalents). If missing, add 'structure_missing'.
- If content seems speculative without sources, add 'speculative' and set ok=false.
- If privacy/safety concerns appear, add 'unsafe' and set ok=false.
- Otherwise ok=true.
Keep 'brief' concise; no extra text beyond the JSON.
"""

guardrail_input_agent  = Agent(name="GuardrailInput",  instructions=INPUT_GUARDRAIL_INSTRUCTIONS,  model="gpt-4o-mini", output_type=SimpleGuardrailOutput)
guardrail_output_agent = Agent(name="GuardrailOutput", instructions=OUTPUT_GUARDRAIL_INSTRUCTIONS, model="gpt-4o-mini", output_type=SimpleGuardrailOutput)

@input_guardrail
async def guardrail_input(ctx, agent, message):
    query_only = _extract_query_only(message)
    res = await Runner.run(guardrail_input_agent, query_only, context=ctx.context)
    g = res.final_output_as(SimpleGuardrailOutput)

    hard_flags = {"unsafe", "illegal", "pii", "adult", "private_data"}
    trip = any(f in hard_flags for f in (g.flags or []))

    return GuardrailFunctionOutput(
        output_info={
            "flags": g.flags,
            "brief": g.brief or "No reason provided by the guardrail agent.",
        },
        tripwire_triggered=trip,
    )

@output_guardrail
async def guardrail_output(ctx, agent, message):
    res = await Runner.run(guardrail_output_agent, message, context=ctx.context)
    g = res.final_output_as(SimpleGuardrailOutput)

    hard_flags = {"unsafe", "illegal", "pii", "adult", "private_data", "speculative"}
    trip = any(f in hard_flags for f in (g.flags or []))

    return GuardrailFunctionOutput(
        output_info={
            "flags": g.flags,
            "brief": g.brief or "No reason provided by the guardrail agent.",
        },
        tripwire_triggered=trip,
    )

# --------------------------------------------------------------------------------------
# Manager Agent (agentic orchestration with tools)
# --------------------------------------------------------------------------------------
MANAGER_INSTRUCTIONS = """
You are the Research Manager. Coordinate the research pipeline by calling tools only (no free text except via yield_status).

Inputs you receive:
- QUERY: <text>
- USER_CLARIFICATIONS: <block or "(skipped by user)" or "(none provided)">
- RECIPIENT_EMAIL: <an email or "(none)">

Workflow:
1) Clarify: 
   • If USER_CLARIFICATIONS are "(skipped by user)" or "(none provided)", call clarify_with_llm to produce exactly 3 clarifying questions, and show them via yield_status. 
   • Otherwise, skip clarification.
2) Plan: call plan_with_llm(query=QUERY). Then yield_status("Planning complete").
3) Search: for each search item, call search_once(query=...). After each, yield_status("Search i/N complete").
4) Aggregate: combine all search summaries into RESEARCH_NOTES (plain text).
5) Write: call write_with_llm(original_query=QUERY, clarifications=USER_CLARIFICATIONS, notes=RESEARCH_NOTES) for a 1000+ word Markdown report with sections:
   Executive Summary, Key Findings (with [#] citations), Assumptions & Limitations, Open Questions, and Next Steps.
6) Convert: call convert_to_html(markdown_text=<the report>, doc_title="Research Report").
7) Email (optional): 
   • If RECIPIENT_EMAIL != "(none)", call send_email_to(to_email=RECIPIENT_EMAIL,
     subject=f"Research Report: {QUERY[:80]}", html_body=<converted HTML>).
   • Yield_status("Email sent") after success or "Email failed" if the tool errors.

Constraints:
- Use yield_status between steps to narrate progress.
- Never fabricate outputs; rely on actual tool results.
- Return ONLY the final HTML string from step 6 as your assistant output (not markdown or other text).
"""

manager_agent = Agent(
    name="Research Manager",
    instructions=MANAGER_INSTRUCTIONS,
    tools=[
        yield_status,
        clarify_tool,
        plan_tool,
        search_once,
        write_tool,
        convert_to_html,
        email_tool,
    ],
    model="gpt-4o-mini",
    model_settings=ModelSettings(tool_choice="required"),
    input_guardrails=[guardrail_input],
    # output_guardrails=[guardrail_output],  # enable if you want final QA gating
)

# --------------------------------------------------------------------------------------
# UI Helpers for Clarifications
# --------------------------------------------------------------------------------------
def _format_user_clarifications(clar):
    if clar.get("skipped"):
        return "USER_CLARIFICATIONS: (skipped by user)"
    lines = ["USER_CLARIFICATIONS:"]
    for i, (q, a) in enumerate(itertools.zip_longest(clar.get("questions", []), clar.get("answers", []), fillvalue="")):
        q = (q or "").strip()
        a = (a or "").strip()
        if q or a:
            lines.append(f"Q{i+1}: {q}" + (f"\nA{i+1}: {a}" if a else ""))
    return "\n".join(lines) if len(lines) > 1 else "USER_CLARIFICATIONS: (none provided)"

async def gen_clarifications(query: str):
    if not (query or "").strip():
        return gr.update(value=""), gr.update(value=""), gr.update(value=""), "Enter a query first."
    res = await Runner.run(clarifier_agent, query.strip())
    qs = res.final_output
    msg = "Generated 3 clarifying questions. You may edit them or add answers, or tick 'Skip' to proceed without."
    return qs.q1, qs.q2, qs.q3, msg

# --------------------------------------------------------------------------------------
# Manager-backed streaming run that yields (status, report HTML) frames
# --------------------------------------------------------------------------------------
async def run_with_clarifications(query: str,
                                  email: str,
                                  q1: str, a1: str,
                                  q2: str, a2: str,
                                  q3: str, a3: str,
                                  skip: bool):
    clar = {
        "skipped": bool(skip),
        "questions": [q1, q2, q3],
        "answers": [a1, a2, a3],
    }
    clar_text = _format_user_clarifications(clar)

    status_md: List[str] = []
    report_html: str = ""

    trace_id = gen_trace_id()
    with trace("Research trace", trace_id=trace_id):
        trace_url = f"https://platform.openai.com/traces/trace?trace_id={trace_id}"
        await STATUS_BUS.publish(f"Trace ready: {trace_url}\n")

        mgr_input = (
            f"QUERY: {query}\n"
            f"{clar_text or 'USER_CLARIFICATIONS: (none provided)'}\n"
            f"RECIPIENT_EMAIL: {(email or '').strip() or '(none)'}\n" 
            "Follow the pipeline and use the tools only. Stream progress via yield_status."
        )

        async def _run_mgr():
            res = await Runner.run(
                manager_agent,
                mgr_input,
                max_turns=25,
            )
            final = getattr(res, "final_output", None) or getattr(res, "output", None)
            return str(final) if final else "Finished (no output)"

        mgr_task = asyncio.create_task(_run_mgr())

        # Live-drain STATUS_BUS while the manager runs
        while not mgr_task.done():
            msg = await STATUS_BUS.get(timeout=0.3)
            if msg:
                status_md.append(f"• {msg}")
                # yield status + whatever report_html we have so far (initially empty)
                yield "\n".join(status_md), report_html

        # Manager now returns **HTML** by contract
        try:
            report_html = await mgr_task  # HTML string
        except InputGuardrailTripwireTriggered as e:
            info = getattr(e.result, "output_info", {}) if hasattr(e, "result") else {}
            flags = set(info.get("flags", []) or [])
            reason = info.get("brief", "The request did not meet safety or clarity requirements.")
            hard_flags = {"unsafe", "illegal", "pii", "adult", "private_data"}
            if flags & hard_flags:
                status_md.append(f"⚠️ Input blocked by guardrails.\nReason: {reason}\nFlags: {', '.join(sorted(flags))}")
                yield "\n".join(status_md), report_html
                return
            # Soft case: surface 3 clarifying questions
            clar = await Runner.run(clarifier_agent, query)
            qs = clar.final_output
            status_md.append("🔎 Clarifying questions:")
            status_md.append(f"1) {qs.q1}")
            status_md.append(f"2) {qs.q2}")
            status_md.append(f"3) {qs.q3}")
            yield "\n".join(status_md), report_html
            return
        except OutputGuardrailTripwireTriggered as e:
            info = getattr(e.result, "output_info", {}) if hasattr(e, "result") else {}
            flags = ", ".join(info.get("flags", [])) or "unspecified"
            reason = info.get("brief", "The draft did not pass quality checks.")
            status_md.append(f"⚠️ Output blocked by guardrails.\nReason: {reason}\nFlags: {flags}")
            yield "\n".join(status_md), report_html
            return
        except Exception as e:
            status_md.append(f"⚠️ Error: {e}")
            yield "\n".join(status_md), report_html
            return

        # Flush any stragglers
        for _ in range(5):
            msg = await STATUS_BUS.get(timeout=0.05)
            if not msg:
                break
            status_md.append(f"• {msg}")

        # Final yield: status + HTML from manager
        yield "\n".join(status_md), report_html

# --------------------------------------------------------------------------------------
# Gradio UI
# --------------------------------------------------------------------------------------
with gr.Blocks(theme=gr.themes.Default(primary_hue="sky")) as ui:
    gr.Markdown("# Deep Research (Agentic Manager)")

    # Top inputs
    with gr.Row():
        query_textbox = gr.Textbox(
            label="What topic would you like to research?",
            lines=3,
            placeholder="e.g., The history and impact of QWERTY"
        )
        user_email = gr.Textbox(
            label="Your email (optional)",
            placeholder="you@example.com"
        )

    # Clarifications panel
    with gr.Accordion("Clarifications", open=True):
        gr.Markdown("You can **auto-generate** clarifying questions or write your own. Answers are optional.")
        with gr.Row():
            gen_button = gr.Button("Auto-generate 3 questions", variant="secondary")
            skip_chk = gr.Checkbox(label="Skip clarifications and proceed", value=False)
        with gr.Row():
            q1 = gr.Textbox(label="Q1")
            a1 = gr.Textbox(label="Answer 1 (optional)")
        with gr.Row():
            q2 = gr.Textbox(label="Q2")
            a2 = gr.Textbox(label="Answer 2 (optional)")
        with gr.Row():
            q3 = gr.Textbox(label="Q3")
            a3 = gr.Textbox(label="Answer 3 (optional)")
        clar_status = gr.Markdown(visible=True)

    # Run button
    run_button = gr.Button("Run Research", variant="primary")

    # Status (own row so Report can be truly full width below)
    with gr.Row():
        status_panel = gr.Markdown(label="Status", value="(waiting…)", elem_id="status-panel")

    # Final Report as HTML (full width)
    with gr.Row():
        report = gr.HTML(label="Final Report", elem_classes=["fullwidth-report"])

    # Wire actions
    gen_button.click(
        fn=gen_clarifications,
        inputs=[query_textbox],
        outputs=[q1, q2, q3, clar_status]
    )

    run_button.click(
        fn=run_with_clarifications,
        inputs=[query_textbox, user_email, q1, a1, q2, a2, q3, a3, skip_chk],
        outputs=[status_panel, report]
    )

# Queue so generator yields stream to UI
ui.queue()

# CSS MUST be set BEFORE launch
ui.css = """
/* Let the whole app span the viewport width */
.gradio-container { max-width: 100% !important; }

/* Make the final report section truly full width */
.fullwidth-report {
  width: 100% !important;
  max-width: 100% !important;
  padding: 0 20px;            /* tasteful side padding */
  box-sizing: border-box;
}

/* Ensure nested nodes don’t clamp width */
.fullwidth-report * {
  max-width: 100% !important;
}

/* Optional: keep status compact and readable */
#status-panel {
  max-height: 40vh;
  overflow: auto;
  border: 1px solid #e6e6e6;
  padding: 10px;
  border-radius: 8px;
  background: #fafafa;
}
"""

ui.launch(inbrowser=True)
