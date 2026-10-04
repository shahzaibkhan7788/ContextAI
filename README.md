# ContextFlow

**Turn scattered information into the next right action.**

ContextFlow is a prototype AI context and action engine. It combines emails, contracts, invoices, policies, support tickets, and notes into a prioritized work queue with source evidence, transparent evidence confidence, missing-information checks, and a human approval step.

## Start on Windows

Open PowerShell in this folder and run these commands **one at a time**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` in that terminal, then activate again. Keep the terminal open and visit the **Local URL** printed by Streamlit (usually http://localhost:8501).

On macOS or Linux, activate with `source .venv/bin/activate`.

## Try the demo

Open the app and choose **Try the Acme demo** or **Load demo scenario**. Five synthetic records show:

1. A **high-priority invoice discrepancy**: $2,400 invoiced versus $1,800 in the agreement, a calculated $600 difference, and a finance-policy threshold above $500.
2. A **contract renewal date** with its source and year.
3. A **low-priority open support follow-up**.

Open an action to inspect the cited source excerpts, missing information, and suggested response draft. Approve, edit, or ignore an action to record a local human decision. Nothing is sent or changed outside this prototype.

## Features

- Multiple PDF, TXT, MD, JSON, and CSV inputs; 10 MB per-file limit.
- Local parsing, source-attributed chunking, and retrieval. BM25 works out of the box without model downloads.
- One ContextFlow Analyst with structured output through an optional OpenAI-compatible API.
- Exact-quote validation for supplemental LLM actions; deterministic Python rules for invoice arithmetic, review thresholds, deadlines, priority safeguards, and missing evidence.
- Evidence-backed action cards, queue filters, response drafts, and local Approve / Edit / Ignore decisions.
- SQLite persistence for source documents, analysis results, and action decisions.

## Configure the optional LLM

Copy `.env.example` to `.env`, add your API key, and restart the app:

```powershell
Copy-Item .env.example .env
```

Set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in `.env` or Streamlit Cloud secrets. For Gemini, run `.\scripts\set-gemini-key.ps1` in PowerShell and enter the key at its hidden prompt. It configures Google's OpenAI-compatible endpoint and `gemini-3.8-flash`. Without both the base URL and key, all analysis stays in local rule-based mode. When configured, the LLM receives retrieved excerpts from your documents; use only a provider appropriate for the information you upload. Never commit `.env` or Streamlit secrets.

## Optional local vector search

To use the configurable `all-MiniLM-L6-v2` embeddings with a local FAISS index instead of the default BM25 fallback:

```powershell
python -m pip install -r requirements-rag.txt
```

Then set `CONTEXTFLOW_USE_FAISS=true` in `.env` and restart the app. The sentence-transformer model is downloaded on first use and run locally; no document vectors are sent to a vector database. The default BM25 mode avoids the larger ML dependencies.

## Tests

```powershell
python -m pytest
```

The synthetic test cases cover supported file formats, unsupported scanned-PDF behavior, evidence retrieval, a policy-backed invoice discrepancy, a renewal date, support follow-up, and a billing concern where the invoice is missing. The project does not claim evaluation percentages.

## Project structure

```text
ContextFlowAI/
├── app.py
├── requirements.txt
├── requirements-rag.txt
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── ingestion.py
│   ├── retrieval.py
│   ├── agent.py
│   ├── analysis.py
│   ├── rules.py
│   └── storage.py
├── ui/
│   ├── __init__.py
│   ├── components.py
│   └── styles.py
├── data/
│   └── demo/
│       ├── customer_email.txt
│       ├── invoice_8821.txt
│       ├── contract.txt
│       ├── finance_policy.txt
│       └── support_ticket.json
├── tests/
│   ├── test_ingestion.py
│   ├── test_retrieval.py
│   └── test_rules.py
├── docs/
│   └── architecture.md
└── .streamlit/
    └── config.toml
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the Mermaid pipeline and trust boundaries.

## Deliberate prototype limits

- No production authentication, multi-user tenancy, or external Gmail / Slack / Teams / CRM integrations.
- No OCR: image-only PDFs return a clear unsupported-file message.
- No autonomous execution, email sending, payment activity, background workers, or external writes.
- Evidence confidence is a transparent heuristic score based on source coverage, not a calibrated probability.
- Uploaded text and analyses persist in `.contextflow/contextflow.sqlite3` on this machine. Use **Clear local workspace** in the sidebar to delete saved workspace records.
- Streamlit Community Cloud deployment is supported by the project shape but has **not** been performed or claimed.

## Future integrations

Gmail, Slack, Microsoft Teams, CRM, ticketing, and workflow systems are possible future inputs. None are implemented in this MVP.
