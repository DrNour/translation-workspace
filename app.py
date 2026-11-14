import io
import json
import re
from datetime import datetime
from xml.etree import ElementTree

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process


st.set_page_config(
    page_title="LinguaDesk — Translator & Interpreter Workbench",
    page_icon="🌐",
    layout="wide",
)


DEFAULT_TERMS = [
    {"source": "artificial intelligence", "target": "الذكاء الاصطناعي", "notes": "Use consistently", "genre": "General"},
    {"source": "machine translation", "target": "الترجمة الآلية", "notes": "Preferred term", "genre": "General"},
    {"source": "quality assurance", "target": "ضمان الجودة", "notes": "", "genre": "General"},
]

GENRES = ["General", "Legal", "Medical", "Technical", "Financial", "Academic", "Marketing", "News", "Literary", "Conference interpreting"]


def init_state():
    defaults = {
        "segments": [],
        "terms": DEFAULT_TERMS.copy(),
        "tm": [],
        "corpus": [],
        "briefing_notes": "",
        "genre": "General",
        "project_name": "Client project",
        "language_pair": "English → Arabic",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def extract_numbers(text):
    return re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text or "")


def check_segment(source, target, terms):
    issues = []
    source_numbers = extract_numbers(source)
    target_numbers = extract_numbers(target)
    for number in source_numbers:
        if number not in target_numbers:
            issues.append(f"Number missing or changed: {number}")

    lowered_target = (target or "").casefold()
    for term in terms:
        source_term = term["source"].strip()
        target_term = term["target"].strip()
        if source_term and source_term.casefold() in (source or "").casefold():
            if target_term and target_term.casefold() not in lowered_target:
                issues.append(f"Glossary term not used: {source_term} → {target_term}")
    return issues


def segment_table():
    if not st.session_state.segments:
        return pd.DataFrame(columns=["#", "Source", "Target", "Status", "Issues"])
    rows = []
    for index, segment in enumerate(st.session_state.segments, start=1):
        issues = check_segment(segment["source"], segment["target"], st.session_state.terms)
        rows.append({
            "#": index,
            "Source": segment["source"],
            "Target": segment["target"],
            "Status": "Needs review" if issues else "Ready",
            "Issues": "; ".join(issues),
        })
    return pd.DataFrame(rows)


def add_segment(source, target):
    source, target = source.strip(), target.strip()
    if source:
        st.session_state.segments.append({
            "source": source,
            "target": target,
            "genre": st.session_state.genre,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })


def import_table(upload):
    if upload.name.lower().endswith((".xlsx", ".xls")):
        frame = pd.read_excel(upload)
    elif upload.name.lower().endswith(".json"):
        data = json.load(upload)
        frame = pd.DataFrame(data if isinstance(data, list) else data.get("terms", data.get("tm", [])))
    else:
        frame = pd.read_csv(upload, sep=None, engine="python")
    frame.columns = [str(c).strip().casefold() for c in frame.columns]
    source_col = next((c for c in frame.columns if c in {"source", "src", "term", "source term", "source segment"}), None)
    target_col = next((c for c in frame.columns if c in {"target", "tgt", "translation", "preferred target", "target segment"}), None)
    if not source_col or not target_col:
        raise ValueError("The file needs source and target columns.")
    return [{"source": str(row[source_col]), "target": str(row[target_col]),
             "notes": str(row.get("notes", "")), "genre": str(row.get("genre", "General"))}
            for _, row in frame.dropna(subset=[source_col, target_col]).iterrows()]


def import_tmx(upload):
    root = ElementTree.fromstring(upload.getvalue())
    rows = []
    for unit in root.iter():
        if unit.tag.split("}")[-1] != "tu":
            continue
        variants = [child for child in unit.iter() if child.tag.split("}")[-1] == "tuv"]
        if len(variants) >= 2:
            texts = [" ".join(node.itertext()).strip() for node in variants[:2]]
            rows.append({"source": texts[0], "target": texts[1], "domain": "Imported TM"})
    return rows


def tm_matches(query, limit=5):
    if not query.strip() or not st.session_state.tm:
        return []
    choices = [x["source"] for x in st.session_state.tm]
    return [(st.session_state.tm[i], round(score)) for _, score, i in process.extract(query, choices, scorer=fuzz.token_set_ratio, limit=limit, score_cutoff=45)]


def corpus_matches(query):
    words = query.casefold().split()
    return [x for x in st.session_state.corpus if all(word in x["text"].casefold() for word in words)] if words else []


def project_json():
    payload = {
        "project": "LinguaDesk",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "segments": st.session_state.segments,
        "terms": st.session_state.terms,
        "tm": st.session_state.tm,
        "corpus": st.session_state.corpus,
        "genre": st.session_state.genre,
        "briefing_notes": st.session_state.briefing_notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


init_state()

st.title("🌐 LinguaDesk")
st.caption("A focused workbench for translators and interpreters")

with st.sidebar:
    st.header("Project")
    st.session_state.project_name = st.text_input("Project name", st.session_state.project_name)
    st.session_state.language_pair = st.selectbox("Language pair", ["English → Arabic", "Arabic → English", "French → English", "Custom"], index=["English → Arabic", "Arabic → English", "French → English", "Custom"].index(st.session_state.language_pair))
    if st.session_state.language_pair == "Custom":
        st.session_state.language_pair = st.text_input("Custom language pair", "Source → Target")
    st.session_state.genre = st.selectbox("Genre / assignment type", GENRES, index=GENRES.index(st.session_state.genre))
    st.divider()
    st.metric("Segments", len(st.session_state.segments))
    st.metric("TM entries", len(st.session_state.tm))
    st.metric("Corpus texts", len(st.session_state.corpus))
    ready_count = int((segment_table()["Status"] == "Ready").sum()) if st.session_state.segments else 0
    st.metric("Ready", ready_count)
    st.download_button("Download project JSON", project_json(), f"{st.session_state.project_name.replace(' ', '_')}.json", "application/json")

tabs = st.tabs(["Translation workspace", "Glossary", "Translation memory", "Corpus & scraping", "QA checker", "Interpreter prep"])

with tabs[0]:
    st.subheader(f"{st.session_state.project_name} · {st.session_state.language_pair} · {st.session_state.genre}")
    st.write("Add source segments and working translations. Glossary and QA checks update automatically.")
    with st.form("segment_form", clear_on_submit=True):
        source = st.text_area("Source segment", height=100, placeholder="Paste a sentence or segment here…")
        target = st.text_area("Translation", height=100, placeholder="Write or paste the translation here…")
        submitted = st.form_submit_button("Add segment", type="primary")
    if submitted:
        if source.strip():
            add_segment(source, target)
            st.success("Segment added.")
        else:
            st.warning("Add a source segment first.")

    if source.strip():
        suggestions = tm_matches(source)
        if suggestions:
            st.info("Translation-memory suggestions")
            for item, score in suggestions:
                st.write(f"**{score}%** · {item['source']} → {item['target']}")

    table = segment_table()
    if not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True, column_config={"Issues": st.column_config.TextColumn(width="large")})
        if st.button("Clear all segments", type="secondary"):
            st.session_state.segments = []
            st.rerun()
    else:
        st.info("Your translation segments will appear here.")

with tabs[1]:
    st.subheader("Terminology glossary")
    st.write("Keep preferred terms visible while you work. The QA checker flags source terms whose approved target is missing.")
    glossary_upload = st.file_uploader("Upload glossary (CSV, TSV, XLSX, JSON)", type=["csv", "tsv", "xlsx", "xls", "json"], key="glossary_upload")
    if glossary_upload and st.button("Import glossary"):
        try:
            imported = import_table(glossary_upload)
            st.session_state.terms.extend(imported)
            st.success(f"Imported {len(imported)} glossary entries.")
        except Exception as exc:
            st.error(str(exc))
    with st.form("term_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 1, 1])
        term_source = c1.text_input("Source term")
        term_target = c2.text_input("Preferred target")
        term_notes = c3.text_input("Notes")
        add_term = st.form_submit_button("Add term")
    if add_term:
        if term_source.strip() and term_target.strip():
            st.session_state.terms.append({"source": term_source.strip(), "target": term_target.strip(), "notes": term_notes.strip()})
            st.success("Term added.")
        else:
            st.warning("Both source and preferred target are required.")

    glossary = pd.DataFrame(st.session_state.terms)
    if not glossary.empty:
        st.dataframe(glossary, use_container_width=True, hide_index=True)
        st.download_button("Export glossary CSV", glossary.to_csv(index=False).encode("utf-8-sig"), "linguadesk_glossary.csv", "text/csv")
        remove_term = st.selectbox("Remove a term", ["—"] + [f"{x['source']} → {x['target']}" for x in st.session_state.terms])
        if remove_term != "—" and st.button("Remove selected term"):
            source_to_remove = remove_term.split(" → ")[0]
            st.session_state.terms = [x for x in st.session_state.terms if x["source"] != source_to_remove]
            st.rerun()

with tabs[2]:
    st.subheader("Translation memory")
    st.write("Create a reusable TM from completed segments or import TMX/CSV/XLSX/JSON.")
    if st.button("Add completed segments to TM"):
        completed = [{"source": x["source"], "target": x["target"], "domain": st.session_state.genre} for x in st.session_state.segments if x["target"].strip()]
        st.session_state.tm.extend(completed)
        st.success(f"Added {len(completed)} entries.")
    tm_upload = st.file_uploader("Upload translation memory", type=["tmx", "csv", "tsv", "xlsx", "xls", "json"], key="tm_upload")
    if tm_upload and st.button("Import translation memory"):
        try:
            imported = import_tmx(tm_upload) if tm_upload.name.lower().endswith(".tmx") else import_table(tm_upload)
            st.session_state.tm.extend(imported)
            st.success(f"Imported {len(imported)} entries.")
        except Exception as exc:
            st.error(str(exc))
    tm_query = st.text_input("Search translation memory", placeholder="Type a source segment…")
    for item, score in tm_matches(tm_query, 10):
        st.write(f"**{score}%** · {item['source']} → {item['target']} · *{item.get('domain', '')}*")
    if st.session_state.tm:
        st.dataframe(pd.DataFrame(st.session_state.tm), use_container_width=True, hide_index=True)
        st.download_button("Export TM as CSV", pd.DataFrame(st.session_state.tm).to_csv(index=False).encode("utf-8-sig"), "linguadesk_tm.csv", "text/csv")

with tabs[5]:
    st.subheader("Corpus research and text collection")
    st.write("Upload local reference texts or extract readable text from public webpages for terminology research.")
    corpus_upload = st.file_uploader("Upload corpus text", type=["txt", "csv", "json", "docx"], key="corpus_upload")
    if corpus_upload and st.button("Add uploaded text"):
        try:
            if corpus_upload.name.lower().endswith(".txt"):
                text = corpus_upload.getvalue().decode("utf-8", errors="ignore")
            elif corpus_upload.name.lower().endswith(".docx"):
                from docx import Document
                text = "\n".join(p.text for p in Document(io.BytesIO(corpus_upload.getvalue())).paragraphs)
            elif corpus_upload.name.lower().endswith(".json"):
                data = json.load(corpus_upload)
                text = "\n".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in (data if isinstance(data, list) else [data]))
            else:
                frame = pd.read_csv(corpus_upload, sep=None, engine="python")
                text = "\n".join(frame.astype(str).apply(" ".join, axis=1))
            st.session_state.corpus.append({"title": corpus_upload.name, "text": text, "source": "Uploaded"})
            st.success("Text added to corpus.")
        except Exception as exc:
            st.error(str(exc))
    url = st.text_input("Public webpage URL", placeholder="https://example.org/article")
    if st.button("Fetch webpage text"):
        try:
            response = requests.get(url, timeout=15, headers={"User-Agent": "LinguaDesk/1.0"})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            title = soup.title.get_text(strip=True) if soup.title else url
            st.session_state.corpus.append({"title": title, "text": text, "source": url})
            st.success("Webpage text added to corpus.")
        except Exception as exc:
            st.error(f"Could not fetch that page: {exc}")
    corpus_query = st.text_input("Search corpus", placeholder="term or phrase")
    results = corpus_matches(corpus_query)
    for row in results[:20]:
        st.markdown(f"**{row['title']}** · {row['source']}\n\n{row['text'][:700]}…")
    st.caption(f"{len(results)} matching text(s). Respect terms, robots rules, copyright, and privacy when collecting texts.")

with tabs[4]:
    st.subheader("Quality assurance")
    st.write("This lightweight checker catches missing numbers and preferred glossary terms before delivery.")
    if st.session_state.segments:
        qa = segment_table()
        issue_rows = qa[qa["Status"] == "Needs review"]
        if issue_rows.empty:
            st.success("No issues found in the current segments.")
        else:
            st.warning(f"{len(issue_rows)} segment(s) need review.")
            st.dataframe(issue_rows, use_container_width=True, hide_index=True)
        csv = qa.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download QA report (CSV)", csv, "linguadesk_qa_report.csv", "text/csv")
    else:
        st.info("Add segments in the Translation workspace to run QA.")

with tabs[3]:
    st.subheader("Interpreter preparation")
    st.write("Capture context, names, numbers, abbreviations, and questions before a live assignment.")
    st.session_state.briefing_notes = st.text_area(
        "Briefing notes",
        value=st.session_state.briefing_notes,
        height=260,
        placeholder="Event purpose…\nKey people and names…\nTechnical terms…\nNumbers and dates to verify…\nQuestions for the client…",
    )
    c1, c2 = st.columns(2)
    c1.download_button("Download briefing notes", st.session_state.briefing_notes.encode("utf-8"), "interpreter_briefing.txt", "text/plain")
    c2.info("Tip: build a glossary from the briefing before the assignment starts.")

st.divider()
st.caption("LinguaDesk MVP · Designed for translator and interpreter workflows · No data leaves this app")
