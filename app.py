import io
import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="LinguaDesk — Translator & Interpreter Workbench",
    page_icon="🌐",
    layout="wide",
)


DEFAULT_TERMS = [
    {"source": "artificial intelligence", "target": "الذكاء الاصطناعي", "notes": "Use consistently"},
    {"source": "machine translation", "target": "الترجمة الآلية", "notes": "Preferred term"},
    {"source": "quality assurance", "target": "ضمان الجودة", "notes": ""},
]


def init_state():
    defaults = {
        "segments": [],
        "terms": DEFAULT_TERMS.copy(),
        "briefing_notes": "",
        "glossary_filter": "",
        "last_check": None,
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
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })


def project_json():
    payload = {
        "project": "LinguaDesk",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "segments": st.session_state.segments,
        "terms": st.session_state.terms,
        "briefing_notes": st.session_state.briefing_notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


init_state()

st.title("🌐 LinguaDesk")
st.caption("A focused workbench for translators and interpreters")

with st.sidebar:
    st.header("Project")
    project_name = st.text_input("Project name", "Client project")
    language_pair = st.selectbox("Language pair", ["English → Arabic", "Arabic → English", "French → English", "Custom"])
    if language_pair == "Custom":
        language_pair = st.text_input("Custom language pair", "Source → Target")
    st.divider()
    st.metric("Segments", len(st.session_state.segments))
    ready_count = int((segment_table()["Status"] == "Ready").sum()) if st.session_state.segments else 0
    st.metric("Ready", ready_count)
    st.download_button("Download project JSON", project_json(), f"{project_name.replace(' ', '_')}.json", "application/json")

tabs = st.tabs(["Translation workspace", "Glossary", "QA checker", "Interpreter prep"])

with tabs[0]:
    st.subheader(f"{project_name} · {language_pair}")
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
        remove_term = st.selectbox("Remove a term", ["—"] + [f"{x['source']} → {x['target']}" for x in st.session_state.terms])
        if remove_term != "—" and st.button("Remove selected term"):
            source_to_remove = remove_term.split(" → ")[0]
            st.session_state.terms = [x for x in st.session_state.terms if x["source"] != source_to_remove]
            st.rerun()

with tabs[2]:
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
