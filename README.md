
# Deep Research — Clean Repo (HF: `research_agent.py`, Local: `deep_research.py`)

This repository is organized so that:
- **Hugging Face Space runs `research_agent.py`**
- **Local Gradio testing runs `deep_research.py`**
- `notifier_agent.py` in GitHub is a **NO-OP stub**. Keep your real notifier **private on HF** only.

![Architecture](docs/assets/architecture.png)

## Run Locally (Gradio)
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python deep_research.py
```

## Hugging Face Space
`research_agent.py` is the entry. In your Space settings (YAML):
```yaml
---
title: Deep_Research
app_file: research_agent.py
sdk: gradio
sdk_version: 5.34.2
---
```

### Hiding the Notifier
- The public repo ships **`notifier_agent.py`** as a no-op stub.
- To enable notifications **only on HF**, create a **private** file `notifier_agent.py` in the HF Space repo (via the web editor) with your real implementation (e.g., Pushover).  
- The public GitHub repo should **not** include your real notifier.  
- Env vars required on HF (set in Space Secrets):
  - `PUSHOVER_TOKEN`
  - `PUSHOVER_USER`

## Environment
```
OPENAI_API_KEY=sk-...
SENDGRID_API_KEY=...        # optional
PUSHOVER_TOKEN=...          # optional (HF only)
PUSHOVER_USER=...           # optional (HF only)
```

## Files
- `research_agent.py` — orchestrator for HF
- `deep_research.py` — local-only Gradio UI
- `planner_agent.py`, `search_agent.py`, `writer_agent.py`, `email_agent.py`
- `notifier_agent.py` — **NO-OP stub** (real notifier lives only on HF Space)
- `docs/assets/architecture.png`

## Embed (Website)
```html
<iframe
  src="https://huggingface.co/spaces/AMIXXM/Deep_Research?embed=true"
  width="850"
  height="600"
  style="border:none;border-radius:8px"
></iframe>
```

## LinkedIn Launch (short)
> 🚀 **Deep Research — now live on Hugging Face**  
> Planner → parallel Search → Writer → optional Email/Notify, orchestrated in `research_agent.py`.  
> Try it: https://huggingface.co/spaces/AMIXXM/Deep_Research
