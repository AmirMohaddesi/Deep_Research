from pydantic import BaseModel, Field
from agents import Agent

HOW_MANY_SEARCHES = 3

PLAN_INSTRUCTIONS = (
    f"You are a helpful research assistant. Given a query, produce exactly {HOW_MANY_SEARCHES} "
    "web search items that, together, best answer the query."
)

class WebSearchItem(BaseModel):
    reason: str = Field(description="Why this search helps answer the query.")
    query: str = Field(description="The exact search term to run.")

class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(description="The searches to perform.")

planner_agent = Agent(
    name="PlannerAgent",
    instructions=PLAN_INSTRUCTIONS,
    model="gpt-4o-mini",
    output_type=WebSearchPlan,
)
