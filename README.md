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

## Suggested next milestones

1. Import DOCX/TXT files and split them into segments.
2. Add translation-memory search across previous projects.
3. Add side-by-side revision history and editing-time analytics.
4. Add optional LLM-assisted suggestions behind a user-provided API key.
5. Add user accounts and a database for shared glossaries.
