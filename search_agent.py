from agents import Agent, WebSearchTool, ModelSettings, function_tool
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
# --------------------------------------------------------------------------------------
# Agents: Search / Planner / Writer
# --------------------------------------------------------------------------------------
class SearchSummary(BaseModel):
    summary: str = Field(description="<=300-word synthesis.")
    sources: List[str] = Field(description="2–5 canonical source URLs, most relevant first.")


SEARCH_INSTRUCTIONS = (
    "You are a research assistant. Given a search term, you search the web for that term and "
    "produce JSON with (1) a <=300-word synthesis in 'summary', and (2) 2–5 canonical source URLs in 'sources'. "
    "Prefer primary/official docs and high-quality outlets; dedupe mirrors. "
    "Return only the JSON fields."
)

search_agent = Agent(
    name="Search agent",
    instructions=SEARCH_INSTRUCTIONS,
    tools=[WebSearchTool(search_context_size="low")],
    model="gpt-4o-mini",
    model_settings=ModelSettings(tool_choice="required"),
    output_type=SearchSummary,
)