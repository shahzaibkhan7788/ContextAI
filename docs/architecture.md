# ContextFlow architecture

```mermaid
flowchart TD
    A[PDF, TXT, MD, JSON, CSV] --> B[Local ingestion and validation]
    B --> C[Text chunks with source IDs]
    C --> D[Local evidence retrieval]
    D -->|Default| E[BM25 keyword retrieval]
    D -->|Optional| F[Sentence Transformers + FAISS]
    E --> G[One ContextFlow Analyst]
    F --> G
    G -->|Optional configured API| H[OpenAI-compatible LLM]
    G --> I[Structured, quote-validated candidates]
    B --> J[Deterministic amount, date, and priority rules]
    I --> K[Evidence-backed work queue]
    J --> K
    K --> L[Human approval, edit, or ignore]
    L --> M[Local SQLite records]
```

## Trust boundaries

- Uploaded documents are parsed and indexed locally. Text-readable PDFs are supported; OCR is not.
- Keyword retrieval runs without model downloads. Optional embedding mode loads the configured Sentence Transformers model locally and indexes vectors in FAISS.
- When LLM variables are configured, only retrieved excerpts and candidate findings are sent to that configured endpoint. LLM suggestions are kept only when cited exact quotations are found in uploaded documents.
- Arithmetic, thresholds, deadline normalization, and known priority rules are implemented in Python.
- Approval, edits, and ignored states are local prototype records. No external action is executed.
- SQLite stores uploaded document text, analysis results, and action state under `.contextflow/`. Clear the workspace in the sidebar to remove those records.
