# LinguaDesk

LinguaDesk is a Streamlit-based translator and interpreter workbench for terminology management, corpus research, translation memory, translation QA, and interpreter briefing preparation.

## Features

- Translation workspace for source and target segments
- Genre-aware project profiles for legal, medical, technical, financial, academic, marketing, news, literary, and conference-interpreting work
- Preferred-term glossary with CSV, TSV, XLSX, and JSON import/export
- Translation-memory creation from completed segments
- TMX, CSV, TSV, XLSX, and JSON translation-memory import/export
- Fuzzy translation-memory matching while translating
- Local corpus uploads and searchable corpus snippets
- Public webpage text extraction for corpus research
- CAT-style segment editing with statuses, effort signals, edit counts, and genre labels
- DOCX translation export
- TXT, DOCX, PDF, CSV, and TSV document upload with automatic segmentation
- XLIFF import/export for professional localization workflows
- Project JSON save/load for portable project snapshots
- Translator analytics and delivery reports
- Revision history and global target search/replace
- Adjustable text size, high-contrast mode, and browser speech playback
- One-click TM application and reviewer/client approval workflow
- Per-segment TM, corpus, and AI translation suggestions
- Optional OpenAI translation through a Streamlit secret (`OPENAI_API_KEY`)
- Concordance-in-context search and corpus word-frequency analysis
- Duplicate TM cleanup and project-level analytics signals
- QA checks for missing or changed numbers
- Interpreter preparation notes
- CSV QA report export
- JSON project export
- No paid API or database required

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `requirements.txt`, and `README.md`.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Choose the repository, branch, and `app.py` as the main file.
4. Deploy.

The app stores data in the current browser session. For a production version, add authentication, persistent storage, stronger document segmentation, and a controlled crawling queue. Only collect web content where you have permission and comply with applicable terms, robots rules, copyright, and privacy requirements.

### Enable AI translation

In Streamlit Community Cloud, open **App settings → Secrets** and add:

```toml
OPENAI_API_KEY = "your-api-key"
```

The key is used only when a translator explicitly clicks **Generate AI translation**. AI output is presented as a suggestion and is never accepted automatically.

### Privacy modes

- **Local-only** (default): blocks all external AI requests.
- **Redacted AI**: replaces common emails, URLs, phone numbers, dates, amounts, and identifiers before sending the current segment and selected context.
- **External AI**: sends the current segment and selected TM/corpus context after explicit confirmation.

The app never sends the full uploaded document for translation. Sensitive projects should still be run on an approved private deployment or locally, with the privacy mode and client permissions confirmed before use.

### Commercial Supabase mode

The repository includes `supabase_schema.sql` and an optional Supabase authentication/cloud-project layer. Run the SQL file in the Supabase SQL Editor. The schema is safe to rerun, then add these values to Streamlit Cloud Secrets:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-anon-key"
```

When these secrets are present, LinguaDesk requires authentication and enables protected project save/load. When they are absent, it runs in local demo mode. Never put a Supabase service-role key in the app or repository.

See [`SECURITY.md`](SECURITY.md) and [`COMMERCIAL_ROADMAP.md`](COMMERCIAL_ROADMAP.md) before using the app with client data.

## Suggested next milestones

1. Import DOCX/TXT files and split them into segments.
2. Add translation-memory search across previous projects.
3. Add side-by-side revision history and editing-time analytics.
4. Add optional LLM-assisted suggestions behind a user-provided API key.
5. Add user accounts and a database for shared glossaries.
