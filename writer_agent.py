from pydantic import BaseModel, Field
from agents import Agent


WRITE_INSTRUCTIONS = (
    "You are a senior researcher tasked with writing a cohesive report for a research query. "
    "You will be provided with the original query and summarized research notes.\n"
    "First, outline the structure and flow. Then generate the full report in markdown.\n"
    "The final output should be detailed (1000+ words; ~5–10 pages), well-structured, and readable."
)

class ReportData(BaseModel):
    short_summary: str = Field(description="A short 2–3 sentence summary of the findings.")
    markdown_report: str = Field(description="The final markdown report.")
    follow_up_questions: list[str] = Field(description="Suggested topics to research further.")

writer_agent = Agent(
    name="WriterAgent",
    instructions=WRITE_INSTRUCTIONS,
    model="gpt-4o-mini",
    output_type=ReportData,
)