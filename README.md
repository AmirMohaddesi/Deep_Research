# Deep Research — Multi-Agent System (Gradio + OpenAI)

> An autonomous multi-agent research workflow that clarifies, plans, searches, and synthesizes reports into clean HTML or email-ready outputs.

🔗 **Live Demo on Hugging Face:**  
👉 [https://huggingface.co/spaces/AMIXXM/Deep_Research](https://huggingface.co/spaces/AMIXXM/Deep_Research)

![Architecture](docs/assets/deep_research_architecture.png)

---

## 🧠 Overview
**Deep Research** is a modular AI pipeline that coordinates multiple agents to perform structured, end-to-end research:
- **Clarifier Agent** – asks 3 key clarifying questions to refine ambiguous prompts.  
- **Planner Agent** – decomposes the query into targeted search tasks.  
- **Search Agent** – performs parallel searches and compiles summaries.  
- **Writer Agent** – synthesizes findings into a structured Markdown report.  
- **Email Agent** – (optional) converts the report into HTML and emails it.  
- **Manager Agent** – orchestrates all steps and streams real-time progress to the Gradio UI.

This project is designed for reproducibility, extensibility, and easy deployment on **Hugging Face Spaces**.

---

## ⚙️ Run Locally
```bash
git clone https://github.com/AmirMohaddesi/Deep_Research.git
cd Deep_Research
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python deep_research.py
```

Then open **http://127.0.0.1:7860** in your browser.

---

## 🧩 Environment Variables
Set your API keys in `.env`:
```
OPENAI_API_KEY=sk-...
SENDGRID_API_KEY=...   # optional, for Email Agent
```

*(Use Hugging Face “Repository Secrets” for secure deployment.)*

---

## 🚀 Deploy on Hugging Face Spaces
`research_agent.py` is the Space entry point.

In your Space configuration (`README` header or Settings → Metadata):

```yaml
---
title: Deep_Research
app_file: research_agent.py
sdk: gradio
sdk_version: 5.34.2
---
```

The Space will automatically install dependencies from `requirements.txt` and start serving the Gradio UI.

### Embed on your website
```html
<iframe
  src="https://huggingface.co/spaces/AMIXXM/Deep_Research?embed=true"
  width="850"
  height="600"
  style="border:none;border-radius:8px"
></iframe>
```

---

## 🧱 Architecture Summary
1. **User Input** → Clarifier Agent → Planner Agent  
2. **Planner Output** → parallel Search Agents → Writer Agent  
3. **Writer Output** → HTML Converter → (optional) Email Agent  
4. **Status** updates streamed through `yield_status`  
5. **Input/Output Guardrails** ensure safety and factuality  

---

## 💡 Example Use Cases
- Generating literature-style research briefs  
- Compiling multi-source analyses for startups or policy reports  
- Automated academic or technical landscape reviews  

---

## 👨‍💻 Author
**Seyed Amirhosein Mohaddesi**  
Ph.D. in Cognitive Robotics — UC Irvine  
🌐 [Website](https://amirhoseinmohaddesi.github.io) | 🤗 [Hugging Face](https://huggingface.co/AMIXXM) | 🧩 [GitHub](https://github.com/AmirMohaddesi)

---

## 🪶 License
MIT License — free for research and commercial use.
