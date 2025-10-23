import os
from typing import Dict

# SendGrid (for optional email delivery)
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from agents import Agent, function_tool

@function_tool
def send_email_to(to_email: str, subject: str, html_body: str) -> Dict[str, str]:
    """
    Send an email (HTML) to a recipient via SendGrid.
    Expects SENDGRID_API_KEY in environment and a verified sender (from_email).
    """
    sg_key = os.environ.get("SENDGRID_API_KEY")
    if not sg_key:
        return {"status": "skipped", "reason": "SENDGRID_API_KEY not set"}
    try:
        sg = SendGridAPIClient(api_key=sg_key)
        from_email = Email("smohadde@uci.edu")  # <-- must be verified in SendGrid
        to = To((to_email or "").strip())
        content = Content("text/html", html_body)
        mail = Mail(from_email, to, subject, content).get()
        sg.client.mail.send.post(request_body=mail)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

INSTRUCTIONS = """You are able to send a nicely formatted HTML email based on a detailed report.
You will be provided with a detailed report. You should use your tool to send one email, providing the 
report converted into clean, well presented HTML with an appropriate subject line."""

email_agent = Agent(
    name="Email agent",
    instructions=INSTRUCTIONS,
    tools=[send_email_to],
    model="gpt-4o-mini",
)
