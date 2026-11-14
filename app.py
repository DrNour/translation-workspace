import io
import json
import os
import re
from datetime import datetime
from xml.etree import ElementTree

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

from supabase_client import configured as supabase_configured
from supabase_client import create_invitation, create_workspace, latest_project, list_workspaces, refresh_session, reset_password, save_project, sign_in, sign_up


st.set_page_config(
    page_title="LinguaDesk — Translator & Interpreter Workbench",
    page_icon="🌐",
    layout="wide",
)

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        min-width: 330px;
        max-width: 380px;
    }
    [data-testid="stSidebarContent"] {
        padding-left: 1.25rem;
        padding-right: 1.25rem;
        overflow-x: hidden;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] input,
    [data-testid="stSidebar"] [data-testid="stSelectbox"] {
        width: 100%;
        box-sizing: border-box;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
        "ai_suggestion": "",
        "ai_for_segment": None,
        "privacy_mode": "Privacy-first",
        "ai_audit_log": [],
        "revisions": [],
        "client_name": "",
        "delivery_notes": "",
        "workspaces": [],
        "workspace_id": "",
        "workspace_name": "",
        "font_scale": "Standard",
        "high_contrast": False,
        "interpreter_turns": [],
        "interpreter_assignment": "",
        "supabase_access_token": "",
        "supabase_refresh_token": "",
        "supabase_email": "",
        "auth_notice": "",
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
    if source.strip() and target.strip() and source.strip()[-1:] in ".?!" and target.strip()[-1:] not in ".?!":
        issues.append("Sentence-final punctuation may be missing")
    if "  " in (target or ""):
        issues.append("Repeated whitespace")
    if source and not target.strip():
        issues.append("Target is empty")
    source_tags = re.findall(r"<[^>]+>|\{[^}]+\}|\[[^]]+\]", source or "")
    for tag in source_tags:
        if tag not in (target or ""):
            issues.append(f"Placeholder/tag missing: {tag}")
    source_dates = re.findall(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b", source or "")
    for date_value in source_dates:
        if date_value not in (target or ""):
            issues.append(f"Date may be changed: {date_value}")
    source_currency = re.findall(r"(?:[$€£¥]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|AED|GBP))", source or "", flags=re.IGNORECASE)
    for amount in source_currency:
        if amount not in (target or ""):
            issues.append(f"Currency/amount may be changed: {amount}")
    return issues


def segment_table():
    if not st.session_state.segments:
        return pd.DataFrame(columns=["#", "Source", "Target", "Status", "Issues", "Words", "Effort", "Genre"])
    rows = []
    for index, segment in enumerate(st.session_state.segments, start=1):
        issues = check_segment(segment["source"], segment["target"], st.session_state.terms)
        rows.append({
            "#": index,
            "Source": segment["source"],
            "Target": segment["target"],
            "Status": segment.get("status", "Needs review" if issues else "Ready"),
            "Issues": "; ".join(issues),
            "Words": len(segment["source"].split()),
            "Effort": segment.get("effort", "Normal"),
            "Genre": segment.get("genre", st.session_state.genre),
        })
    return pd.DataFrame(rows)


def add_segment(source, target):
    source, target = source.strip(), target.strip()
    if source:
        st.session_state.segments.append({
            "source": source,
            "target": target,
            "genre": st.session_state.genre,
            "status": "Draft" if not target.strip() else "Needs review",
            "effort": "Normal",
            "edit_count": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "review_status": "Pending",
            "reviewer_comment": "",
        })


def record_revision(index, old_target, new_target, action="manual edit"):
    if old_target != new_target:
        st.session_state.revisions.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "segment": index + 1,
            "action": action,
            "old_target": old_target,
            "new_target": new_target,
        })


def import_xliff(upload):
    root = ElementTree.fromstring(upload.getvalue())
    rows = []
    for unit in root.iter():
        if unit.tag.split("}")[-1] != "trans-unit":
            continue
        source = next((x for x in unit if x.tag.split("}")[-1] == "source"), None)
        target = next((x for x in unit if x.tag.split("}")[-1] == "target"), None)
        if source is not None:
            rows.append((" ".join(source.itertext()).strip(), " ".join(target.itertext()).strip() if target is not None else ""))
    return rows


def import_tbx(upload):
    root = ElementTree.fromstring(upload.getvalue())
    rows = []
    for entry in root.iter():
        if entry.tag.split("}")[-1] != "termEntry":
            continue
        terms = []
        for lang_set in entry.iter():
            if lang_set.tag.split("}")[-1] == "langSet":
                lang = lang_set.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                term = " ".join(lang_set.itertext()).strip()
                if term:
                    terms.append((lang, term))
        if len(terms) >= 2:
            rows.append({"source": terms[0][1], "target": terms[1][1], "notes": "Imported TBX", "genre": "General"})
    return rows


def local_transcribe_audio(audio_file, language_hint=""):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local transcription is optional. Install dependencies from requirements-local.txt to enable it.") from exc
    model = WhisperModel("small", device="cpu", compute_type="int8")
    audio_file.seek(0)
    temporary_path = "/tmp/linguadesk_interpreter.wav"
    with open(temporary_path, "wb") as handle:
        handle.write(audio_file.getvalue())
    segments, _ = model.transcribe(temporary_path, language=language_hint or None)
    return " ".join(segment.text.strip() for segment in segments).strip()


def export_xliff():
    root = ElementTree.Element("xliff", {"version": "1.2"})
    file_node = ElementTree.SubElement(root, "file", {"source-language": st.session_state.language_pair.split(" → ")[0], "target-language": st.session_state.language_pair.split(" → ")[-1], "datatype": "x- LinguaDesk"})
    body = ElementTree.SubElement(file_node, "body")
    for index, segment in enumerate(st.session_state.segments, 1):
        unit = ElementTree.SubElement(body, "trans-unit", {"id": str(index)})
        ElementTree.SubElement(unit, "source").text = segment["source"]
        ElementTree.SubElement(unit, "target").text = segment.get("target", "")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def load_project(payload):
    data = json.loads(payload.decode("utf-8"))
    for key in ["segments", "terms", "tm", "corpus", "briefing_notes", "genre", "language_pair", "client_name", "delivery_notes"]:
        if key in data:
            st.session_state[key] = data[key]


def split_into_segments(text):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    segments = []
    for paragraph in paragraphs:
        if len(paragraph) <= 600:
            segments.append(paragraph)
        else:
            segments.extend(x.strip() for x in re.split(r"(?<=[.!?؟。])\s+", paragraph) if x.strip())
    return segments


def extract_document_text(upload):
    name = upload.name.lower()
    data = upload.getvalue()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".docx"):
        from docx import Document
        return "\n\n".join(p.text.strip() for p in Document(io.BytesIO(data)).paragraphs if p.text.strip())
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if name.endswith((".csv", ".tsv")):
        frame = pd.read_csv(io.BytesIO(data), sep="\t" if name.endswith(".tsv") else ",")
        return "\n\n".join(frame.astype(str).apply(" ".join, axis=1))
    raise ValueError("Supported document types are TXT, DOCX, PDF, CSV, and TSV.")


def openai_key():
    try:
        return st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    except Exception:
        return os.getenv("OPENAI_API_KEY")


def redact_text(text):
    """Replace common direct identifiers before any optional external AI request."""
    replacements = []
    patterns = [
        (r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "EMAIL"),
        (r"https?://\S+", "URL"),
        (r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "PHONE"),
        (r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", "DATE"),
        (r"(?:[$€£¥]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|AED|GBP))", "AMOUNT"),
        (r"\b(?:passport|ID|identifier|record|account)[\s:#-]*[A-Z0-9-]{4,}\b", "IDENTIFIER"),
    ]
    redacted = text or ""
    for pattern, label in patterns:
        def replace(match, label=label):
            token = f"[{label}_{len(replacements) + 1}]"
            replacements.append((token, match.group(0)))
            return token
        redacted = re.sub(pattern, replace, redacted, flags=re.IGNORECASE)
    return redacted, replacements


def restore_redactions(text, replacements):
    restored = text or ""
    for token, original in replacements:
        restored = restored.replace(token, original)
    return restored


def ai_translate(source, model, tm_context, corpus_context, privacy_mode):
    key = openai_key()
    if privacy_mode == "Privacy-first":
        raise ValueError("Privacy-first mode blocks external AI requests.")
    if not key:
        raise ValueError("Add OPENAI_API_KEY to Streamlit secrets before using AI translation.")
    if privacy_mode == "Redacted AI":
        redacted_source, source_replacements = redact_text(source)
        redacted_tm, tm_replacements = redact_text(tm_context)
        redacted_corpus, corpus_replacements = redact_text(corpus_context)
        replacements = source_replacements + tm_replacements + corpus_replacements
    else:
        redacted_source, redacted_tm, redacted_corpus, replacements = source, tm_context, corpus_context, []
    term_payload = json.dumps(st.session_state.terms, ensure_ascii=False)
    if privacy_mode == "Redacted AI":
        term_payload, term_replacements = redact_text(term_payload)
        replacements.extend(term_replacements)
    prompt = f"""Translate the source segment into {st.session_state.language_pair.split(' → ')[-1]}.
Genre: {st.session_state.genre}.
Preserve meaning, numbers, names, formatting, and register. Use the terminology and examples as evidence, but do not copy an example when it does not fit. Return only the translation.

Approved terminology:
    {term_payload}

Translation-memory examples:
{redacted_tm or 'None'}

Corpus examples:
{redacted_corpus or 'None'}

Source segment:
{redacted_source}"""
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "instructions": "You are a careful professional translator. Preserve redaction placeholders exactly.", "input": prompt, "store": False},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("output_text"):
        return restore_redactions(payload["output_text"].strip(), replacements)
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("text"):
                return restore_redactions(content["text"].strip(), replacements)
    raise ValueError("The AI service returned no translation text.")


def transcribe_audio(audio_file, language_hint=""):
    key = openai_key()
    if not key:
        raise ValueError("Add OPENAI_API_KEY to use cloud transcription.")
    audio_file.seek(0)
    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (audio_file.name or "recording.wav", audio_file, "audio/wav")},
        data={"model": "whisper-1", "language": language_hint or ""},
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("text", "").strip()


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


def fetch_webpage_text(url):
    response = requests.get(url, timeout=15, headers={"User-Agent": "LinguaDesk/1.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    title = soup.title.get_text(strip=True) if soup.title else url
    return title, text


def concordance(query, window=90):
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    for document in st.session_state.corpus:
        for match in pattern.finditer(document["text"]):
            start, end = max(0, match.start() - window), min(len(document["text"]), match.end() + window)
            results.append({"Context": document["text"][start:end], "Document": document["title"], "Source": document["source"]})
    return results


def corpus_frequency():
    words = re.findall(r"[\w’'-]{3,}", " ".join(x["text"].casefold() for x in st.session_state.corpus), flags=re.UNICODE)
    return pd.Series(words).value_counts().head(50).rename_axis("Word").reset_index(name="Frequency") if words else pd.DataFrame(columns=["Word", "Frequency"])


def export_docx():
    from docx import Document
    document = Document()
    document.add_heading(st.session_state.project_name, 0)
    document.add_paragraph(f"{st.session_state.language_pair} · {st.session_state.genre}")
    for segment in st.session_state.segments:
        document.add_paragraph(segment["source"], style="Intense Quote")
        document.add_paragraph(segment["target"])
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


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
        "ai_audit_log": st.session_state.ai_audit_log,
        "revisions": st.session_state.revisions,
        "client_name": st.session_state.client_name,
        "delivery_notes": st.session_state.delivery_notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


init_state()

if supabase_configured() and not st.session_state.supabase_access_token and st.session_state.supabase_refresh_token:
    try:
        refreshed = refresh_session(st.session_state.supabase_refresh_token)
        st.session_state.supabase_access_token = refreshed.get("access_token", "")
        st.session_state.supabase_refresh_token = refreshed.get("refresh_token", st.session_state.supabase_refresh_token)
    except Exception:
        st.session_state.supabase_access_token = ""
        st.session_state.supabase_refresh_token = ""

if supabase_configured() and not st.session_state.supabase_access_token:
    st.title("🌐 LinguaDesk")
    st.info("Commercial mode is enabled. Sign in to access protected projects.")
    if st.session_state.auth_notice:
        st.success(st.session_state.auth_notice)
    auth_tab_signin, auth_tab_signup, auth_tab_reset = st.tabs(["Sign in", "Create account", "Reset password"])
    with auth_tab_signin:
        with st.form("signin_form"):
            auth_email = st.text_input("Email", key="signin_email")
            auth_password = st.text_input("Password", type="password", key="signin_password")
            auth_submit = st.form_submit_button("Sign in", type="primary")
        if auth_submit:
            try:
                auth_result = sign_in(auth_email, auth_password)
                if auth_result.get("access_token"):
                    st.session_state.supabase_access_token = auth_result["access_token"]
                    st.session_state.supabase_refresh_token = auth_result.get("refresh_token", "")
                    st.session_state.supabase_email = auth_email
                    st.session_state.auth_notice = ""
                    st.rerun()
                st.error("No active session was returned. Confirm your email first.")
            except Exception as exc:
                st.error(f"Sign-in failed: {exc}")
    with auth_tab_signup:
        st.write("Create a LinguaDesk account for protected cloud projects.")
        with st.form("signup_form"):
            signup_email = st.text_input("Email", key="signup_email")
            signup_password = st.text_input("Password", type="password", key="signup_password")
            signup_password_confirm = st.text_input("Confirm password", type="password", key="signup_password_confirm")
            signup_submit = st.form_submit_button("Create account", type="primary")
        if signup_submit:
            if signup_password != signup_password_confirm:
                st.error("The passwords do not match.")
            elif len(signup_password) < 6:
                st.error("Use a password with at least 6 characters.")
            else:
                try:
                    auth_result = sign_up(signup_email, signup_password)
                    if auth_result.get("access_token"):
                        st.session_state.supabase_access_token = auth_result["access_token"]
                        st.session_state.supabase_refresh_token = auth_result.get("refresh_token", "")
                        st.session_state.supabase_email = signup_email
                        st.rerun()
                    st.session_state.auth_notice = "Account created. Check your email, confirm the account, then use the Sign in tab."
                    st.rerun()
                except Exception as exc:
                    st.error(f"Account creation failed: {exc}")
    with auth_tab_reset:
        st.write("Supabase will email you a password-reset link.")
        with st.form("reset_form"):
            reset_email = st.text_input("Account email", key="reset_email")
            reset_submit = st.form_submit_button("Send reset link")
        if reset_submit:
            try:
                reset_password(reset_email)
                st.success("If that account exists, a reset email has been sent.")
            except Exception as exc:
                st.error(f"Password reset failed: {exc}")
    st.stop()

st.title("🌐 LinguaDesk")
st.caption("A focused workbench for translators and interpreters")

with st.sidebar:
    st.header("Project")
    st.session_state.project_name = st.text_input("Project name", st.session_state.project_name)
    st.session_state.client_name = st.text_input("Client / agency", st.session_state.client_name)
    st.session_state.language_pair = st.selectbox("Language pair", ["English → Arabic", "Arabic → English", "French → English", "Custom"], index=["English → Arabic", "Arabic → English", "French → English", "Custom"].index(st.session_state.language_pair))
    if st.session_state.language_pair == "Custom":
        st.session_state.language_pair = st.text_input("Custom language pair", "Source → Target")
    st.session_state.genre = st.selectbox("Genre / assignment type", GENRES, index=GENRES.index(st.session_state.genre))
    if st.session_state.privacy_mode in {"Local-only", "Redacted AI"}:
        st.session_state.privacy_mode = "Privacy-first"
    st.session_state.privacy_mode = st.selectbox("Data mode", ["Privacy-first", "Standard"], index=["Privacy-first", "Standard"].index(st.session_state.privacy_mode))
    if st.session_state.privacy_mode == "Privacy-first":
        st.caption("No text or audio is sent to external AI services. TM, corpus, glossary, and QA remain available.")
    else:
        st.caption("AI translation and transcription are available after explicit confirmation.")
    st.subheader("Accessibility")
    st.session_state.font_scale = st.selectbox("Text size", ["Small", "Standard", "Large", "Extra large"], index=["Small", "Standard", "Large", "Extra large"].index(st.session_state.font_scale))
    st.session_state.high_contrast = st.checkbox("High-contrast interface", value=st.session_state.high_contrast)
    st.divider()
    st.metric("Segments", len(st.session_state.segments))
    st.metric("TM entries", len(st.session_state.tm))
    st.metric("Corpus texts", len(st.session_state.corpus))
    ready_count = int((segment_table()["Status"] == "Ready").sum()) if st.session_state.segments else 0
    st.metric("Ready", ready_count)
    st.download_button("Download project JSON", project_json(), f"{st.session_state.project_name.replace(' ', '_')}.json", "application/json")
    if st.session_state.supabase_access_token:
        st.caption(f"Signed in as {st.session_state.supabase_email}")
        try:
            st.session_state.workspaces = list_workspaces(st.session_state.supabase_access_token)
        except Exception as exc:
            st.warning(f"Could not load workspaces: {exc}")
        if st.session_state.workspaces:
            workspace_labels = [f"{w['name']} ({w['id'][:8]})" for w in st.session_state.workspaces]
            workspace_choice = st.selectbox("Workspace", workspace_labels, key="workspace_choice")
            st.session_state.workspace_id = st.session_state.workspaces[workspace_labels.index(workspace_choice)]["id"]
        with st.expander("Create workspace"):
            new_workspace_name = st.text_input("Workspace name", key="new_workspace_name")
            if st.button("Create workspace") and new_workspace_name.strip():
                try:
                    created = create_workspace(st.session_state.supabase_access_token, new_workspace_name.strip())
                    st.session_state.workspace_id = created["id"]
                    st.success("Workspace created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Workspace creation failed: {exc}")
        if st.session_state.workspace_id:
            with st.expander("Invite team member"):
                invite_email = st.text_input("Member email", key="invite_email")
                invite_role = st.selectbox("Role", ["manager", "translator", "reviewer", "client"], key="invite_role")
                if st.button("Create invitation") and invite_email.strip():
                    try:
                        invitation = create_invitation(st.session_state.supabase_access_token, st.session_state.workspace_id, invite_email, invite_role)
                        st.success(f"Invitation record created for {invitation['email']} as {invitation['role']}.")
                    except Exception as exc:
                        st.error(f"Invitation failed: {exc}")
        if st.button("Save project to cloud"):
            try:
                save_project(st.session_state.supabase_access_token, st.session_state.project_name, json.loads(project_json().decode("utf-8")))
                st.success("Project saved to Supabase.")
            except Exception as exc:
                st.error(f"Cloud save failed: {exc}")
        if st.button("Load latest cloud project"):
            try:
                latest = latest_project(st.session_state.supabase_access_token)
                if latest:
                    load_project(json.dumps(latest["payload"], ensure_ascii=False).encode("utf-8"))
                    st.success(f"Loaded {latest['name']}.")
                    st.rerun()
                else:
                    st.info("No cloud projects found.")
            except Exception as exc:
                st.error(f"Cloud load failed: {exc}")
        if st.button("Sign out"):
            st.session_state.supabase_access_token = ""
            st.session_state.supabase_refresh_token = ""
            st.session_state.supabase_email = ""
            st.rerun()
    project_upload = st.file_uploader("Load project JSON", type=["json"], key="project_upload")
    if project_upload and st.button("Load project"):
        try:
            load_project(project_upload.getvalue())
            st.success("Project loaded.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not load project: {exc}")
    if st.button("Delete all session project data"):
        for key in ["segments", "terms", "tm", "corpus", "briefing_notes", "ai_audit_log", "revisions", "client_name", "delivery_notes"]:
            st.session_state[key] = [] if key in {"segments", "terms", "tm", "corpus", "ai_audit_log"} else ""
        st.session_state.ai_suggestion = ""
        st.session_state.ai_for_segment = None
        st.success("Session project data deleted.")

scale = {"Small": "0.92", "Standard": "1", "Large": "1.12", "Extra large": "1.25"}[st.session_state.font_scale]
contrast_css = "body { filter: contrast(1.12); }" if st.session_state.high_contrast else ""
st.markdown(f"<style>html {{ font-size: {scale}em; }} {contrast_css}</style>", unsafe_allow_html=True)

tabs = st.tabs(["Translation workspace", "Glossary", "Translation memory", "Corpus & scraping", "QA checker", "Interpreter prep", "Review & delivery", "Analytics & delivery"])

with tabs[0]:
    st.subheader(f"{st.session_state.project_name} · {st.session_state.language_pair} · {st.session_state.genre}")
    st.write("Edit, classify, and review segments in a CAT-style workflow. Glossary, TM, and QA signals update automatically.")
    document_upload = st.file_uploader("Upload document to segment", type=["txt", "docx", "pdf", "csv", "tsv", "xlf", "xliff"], key="document_upload")
    if document_upload and st.button("Import document as segments"):
        try:
            if document_upload.name.lower().endswith((".xlf", ".xliff")):
                imported_pairs = import_xliff(document_upload)
                for source_text, target_text in imported_pairs:
                    add_segment(source_text, target_text)
                imported_segments = [x[0] for x in imported_pairs]
            else:
                text = extract_document_text(document_upload)
                imported_segments = split_into_segments(text)
                for segment_text in imported_segments:
                    add_segment(segment_text, "")
            st.success(f"Imported {len(imported_segments)} segments from {document_upload.name}.")
        except Exception as exc:
            st.error(f"Could not import document: {exc}")
    if st.session_state.segments:
        segment_options = [f"{i + 1}. {x['source'][:80]}" for i, x in enumerate(st.session_state.segments)]
        selected_segment = st.selectbox("Open segment", ["—"] + segment_options, key="selected_segment")
        if selected_segment != "—":
            selected_index = segment_options.index(selected_segment)
            current = st.session_state.segments[selected_index]
            tm_suggestions = tm_matches(current["source"], 5)
            corpus_context = concordance(current["source"].split()[0], 3) if st.session_state.corpus and current["source"].split() else []
            if tm_suggestions:
                st.markdown("**Translation-memory suggestions**")
                for item, score in tm_suggestions:
                    st.write(f"{score}% · {item['source']} → {item['target']}")
                if st.button("Use best TM match", key=f"use_tm_{selected_index}"):
                    current["target"] = tm_suggestions[0][0]["target"]
                    current["status"] = "Needs review"
                    current["edit_count"] = current.get("edit_count", 0) + 1
                    record_revision(selected_index, "", current["target"], "TM suggestion applied")
                    st.success("TM suggestion copied into the editor. Review it before approval.")
            with st.expander("Accessibility tools"):
                if st.button("Read source aloud", key=f"speak_source_{selected_index}"):
                    components.html(f"<script>window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance({json.dumps(current['source'])}));</script>", height=0)
                if current.get("target") and st.button("Read target aloud", key=f"speak_target_{selected_index}"):
                    components.html(f"<script>window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance({json.dumps(current['target'])}));</script>", height=0)
            if corpus_context:
                with st.expander("Corpus evidence"):
                    for item in corpus_context:
                        st.write(f"{item['Context']} · {item['Document']}")
            ai_model = st.text_input("AI model", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), key="ai_model")
            ai_confirmed = False
            if st.session_state.privacy_mode != "Privacy-first":
                ai_confirmed = st.checkbox("I confirm this segment and its selected context may be sent to the configured AI provider.")
            if st.button("Generate AI translation", type="secondary", disabled=st.session_state.privacy_mode == "Privacy-first" or not ai_confirmed):
                try:
                    tm_context = "\n".join(f"{item['source']} → {item['target']} ({score}%)" for item, score in tm_suggestions)
                    corpus_text = "\n".join(item["Context"] for item in corpus_context)
                    st.session_state.ai_suggestion = ai_translate(current["source"], ai_model, tm_context, corpus_text, st.session_state.privacy_mode)
                    st.session_state.ai_for_segment = selected_index
                    st.session_state.ai_audit_log.append({"time": datetime.now().isoformat(timespec="seconds"), "segment": selected_index + 1, "mode": st.session_state.privacy_mode, "model": ai_model})
                    st.success("AI suggestion generated. Review it before accepting.")
                except Exception as exc:
                    st.error(str(exc))
            suggested_target = st.session_state.ai_suggestion if st.session_state.ai_for_segment == selected_index else current["target"]
            with st.form("editor_form"):
                edited_target = st.text_area("Target editor", suggested_target, height=130)
                ec1, ec2 = st.columns(2)
                new_status = ec1.selectbox("Segment status", ["Draft", "Needs review", "Reviewed", "Approved"], index=["Draft", "Needs review", "Reviewed", "Approved"].index(current.get("status", "Draft")))
                new_effort = ec2.selectbox("Effort signal", ["Low", "Normal", "High", "Very high"], index=["Low", "Normal", "High", "Very high"].index(current.get("effort", "Normal")))
                reviewer_comment = st.text_input("Reviewer / client comment", current.get("reviewer_comment", ""))
                save_segment = st.form_submit_button("Save segment", type="primary")
            if save_segment:
                if edited_target != current["target"]:
                    current["edit_count"] = current.get("edit_count", 0) + 1
                    record_revision(selected_index, current["target"], edited_target)
                current["target"], current["status"], current["effort"], current["reviewer_comment"] = edited_target, new_status, new_effort, reviewer_comment
                current["last_edited_at"] = datetime.now().isoformat(timespec="seconds")
                st.success("Segment saved.")
            st.caption(f"Source: {current['source']} · Edits: {current.get('edit_count', 0)}")
    st.download_button("Export translated document (DOCX)", export_docx(), "linguadesk_translation.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    st.download_button("Export bilingual XLIFF", export_xliff(), "linguadesk_project.xliff", "application/xml")
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
    glossary_upload = st.file_uploader("Upload glossary (TBX, CSV, TSV, XLSX, JSON)", type=["tbx", "csv", "tsv", "xlsx", "xls", "json"], key="glossary_upload")
    if glossary_upload and st.button("Import glossary"):
        try:
            imported = import_tbx(glossary_upload) if glossary_upload.name.lower().endswith(".tbx") else import_table(glossary_upload)
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
    if st.session_state.tm and st.button("Remove duplicate TM entries"):
        unique = {(x.get("source", "").strip().casefold(), x.get("target", "").strip()): x for x in st.session_state.tm}
        removed = len(st.session_state.tm) - len(unique)
        st.session_state.tm = list(unique.values())
        st.success(f"Removed {removed} duplicate entr{'y' if removed == 1 else 'ies'}.")
    if st.session_state.tm and st.button("Prefill exact TM matches"):
        filled = 0
        for index, segment in enumerate(st.session_state.segments):
            if not segment.get("target", "").strip():
                matches = tm_matches(segment["source"], 1)
                if matches and matches[0][1] >= 98:
                    segment["target"] = matches[0][0]["target"]
                    segment["status"] = "Needs review"
                    record_revision(index, "", segment["target"], "Exact TM prefill")
                    filled += 1
        st.success(f"Prefilled {filled} exact TM match(es). Review before approval.")
    tm_query = st.text_input("Search translation memory", placeholder="Type a source segment…")
    for item, score in tm_matches(tm_query, 10):
        st.write(f"**{score}%** · {item['source']} → {item['target']} · *{item.get('domain', '')}*")
    if st.session_state.tm:
        st.dataframe(pd.DataFrame(st.session_state.tm), use_container_width=True, hide_index=True)
        st.download_button("Export TM as CSV", pd.DataFrame(st.session_state.tm).to_csv(index=False).encode("utf-8-sig"), "linguadesk_tm.csv", "text/csv")

with tabs[3]:
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
            title, text = fetch_webpage_text(url)
            st.session_state.corpus.append({"title": title, "text": text, "source": url})
            st.success("Webpage text added to corpus.")
        except Exception as exc:
            st.error(f"Could not fetch that page: {exc}")
    corpus_query = st.text_input("Search corpus", placeholder="term or phrase")
    results = corpus_matches(corpus_query)
    for row in results[:20]:
        st.markdown(f"**{row['title']}** · {row['source']}\n\n{row['text'][:700]}…")
    st.caption(f"{len(results)} matching text(s). Respect terms, robots rules, copyright, and privacy when collecting texts.")
    if st.session_state.corpus:
        cc1, cc2 = st.columns(2)
        with cc1:
            concordance_term = st.text_input("Concordance term", placeholder="Show term in context")
            concordance_rows = concordance(concordance_term) if concordance_term else []
            if concordance_rows:
                st.dataframe(pd.DataFrame(concordance_rows), use_container_width=True, hide_index=True)
        with cc2:
            st.write("Most frequent corpus words")
            st.dataframe(corpus_frequency(), use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Quality assurance")
    st.write("This lightweight checker catches missing numbers and preferred glossary terms before delivery.")
    if st.session_state.segments:
        qa = segment_table()
        issue_rows = qa[qa["Status"] == "Needs review"]
        if issue_rows.empty:
            st.success("No issues found in the current segments.")
        if not issue_rows.empty:
            st.warning(f"{len(issue_rows)} segment(s) need review.")
            st.dataframe(issue_rows, use_container_width=True, hide_index=True)
        csv = qa.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download QA report (CSV)", csv, "linguadesk_qa_report.csv", "text/csv")
    else:
        st.info("Add segments in the Translation workspace to run QA.")

with tabs[5]:
    st.subheader("Interpreter preparation")
    st.write("Capture context, names, numbers, abbreviations, and questions before a live assignment.")
    st.session_state.interpreter_assignment = st.text_input("Assignment / event", st.session_state.interpreter_assignment)
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
    st.subheader("Interpreter Console")
    st.caption("Use this workspace for consecutive notes, speaker turns, live terminology, and optional dictation.")
    ic1, ic2 = st.columns([1, 2])
    with ic1:
        speaker = st.text_input("Speaker", placeholder="Name or role")
        turn_kind = st.selectbox("Turn type", ["Source turn", "Interpretation", "Question", "Number / name", "Action item"])
        live_term = st.text_input("Quick glossary search", placeholder="term")
        if live_term:
            for term, score in process.extract(live_term, [x["source"] for x in st.session_state.terms], scorer=fuzz.partial_ratio, limit=5):
                matching = next(x for x in st.session_state.terms if x["source"] == term)
                st.write(f"{score}% · **{matching['source']}** → {matching['target']}")
    with ic2:
        turn_note = st.text_area("Live note", height=130, placeholder="Capture the idea, not every word…")
        if st.button("Add turn note") and turn_note.strip():
            st.session_state.interpreter_turns.append({"time": datetime.now().strftime("%H:%M:%S"), "speaker": speaker or "Unassigned", "type": turn_kind, "note": turn_note.strip()})
            st.success("Turn added.")
    with st.expander("Dictation"):
        st.write("Record a note directly from your microphone. In Privacy-first mode, the recording stays available for playback/download and is not sent to a cloud service.")
        audio = st.audio_input("Record interpreter note", sample_rate=16000, key="interpreter_audio")
        if audio:
            st.audio(audio)
            st.download_button("Download recording", audio.getvalue(), "interpreter_note.wav", "audio/wav")
            if st.session_state.privacy_mode == "Privacy-first":
                st.info("Privacy-first mode is active. Cloud transcription is disabled.")
                if st.button("Transcribe locally", key="local_transcribe"):
                    try:
                        transcript = local_transcribe_audio(audio, transcript_language if 'transcript_language' in locals() else "")
                        st.session_state.interpreter_turns.append({"time": datetime.now().strftime("%H:%M:%S"), "speaker": speaker or "Unassigned", "type": "Local dictation", "note": transcript})
                        st.success("Local transcript added to the turn log.")
                    except Exception as exc:
                        st.error(str(exc))
            else:
                transcript_language = st.text_input("Language hint (optional)", placeholder="en or ar", key="transcript_language")
                if st.button("Transcribe recording"):
                    try:
                        transcript = transcribe_audio(audio, transcript_language)
                        st.session_state.interpreter_turns.append({"time": datetime.now().strftime("%H:%M:%S"), "speaker": speaker or "Unassigned", "type": "Dictation", "note": transcript})
                        st.success("Transcript added to the turn log.")
                    except Exception as exc:
                        st.error(f"Transcription failed: {exc}")
    if st.session_state.interpreter_turns:
        st.subheader("Turn log")
        st.dataframe(pd.DataFrame(st.session_state.interpreter_turns), use_container_width=True, hide_index=True)
        st.download_button("Export turn log", pd.DataFrame(st.session_state.interpreter_turns).to_csv(index=False).encode("utf-8-sig"), "interpreter_turn_log.csv", "text/csv")

with tabs[6]:
    st.subheader("Review and delivery")
    st.write("Reviewers and clients can filter segments, leave comments, and approve delivery items.")
    review_rows = []
    for index, segment in enumerate(st.session_state.segments, 1):
        review_rows.append({"#": index, "Source": segment["source"], "Target": segment.get("target", ""), "Translation status": segment.get("status", "Draft"), "Review status": segment.get("review_status", "Pending"), "Comment": segment.get("reviewer_comment", "")})
    review_table = pd.DataFrame(review_rows)
    if review_table.empty:
        st.info("No segments are available for review yet.")
    else:
        review_filter = st.selectbox("Review filter", ["All", "Pending", "Changes requested", "Approved"])
        if review_filter != "All":
            review_table = review_table[review_table["Review status"] == review_filter]
        st.dataframe(review_table, use_container_width=True, hide_index=True)
        review_index = st.selectbox("Open review segment", ["—"] + [str(x) for x in review_table["#"].tolist()])
        if review_index != "—":
            row_index = int(review_index) - 1
            segment = st.session_state.segments[row_index]
            st.write(f"**Source:** {segment['source']}")
            st.write(f"**Target:** {segment.get('target', '')}")
            with st.form("review_form"):
                review_comment = st.text_area("Comment", segment.get("reviewer_comment", ""))
                review_status = st.selectbox("Review decision", ["Pending", "Changes requested", "Approved"], index=["Pending", "Changes requested", "Approved"].index(segment.get("review_status", "Pending")))
                submit_review = st.form_submit_button("Save review")
            if submit_review:
                segment["reviewer_comment"] = review_comment
                segment["review_status"] = review_status
                if review_status == "Approved":
                    segment["status"] = "Approved"
                st.success("Review saved.")

with tabs[7]:
    st.subheader("Translator analytics and delivery")
    table = segment_table()
    total_words = int(table["Words"].sum()) if not table.empty else 0
    translated = int((table["Target"].fillna("").str.strip() != "").sum()) if not table.empty else 0
    approved = int((table["Status"] == "Approved").sum()) if not table.empty else 0
    flagged = int(table["Issues"].fillna("").str.strip().ne("").sum()) if not table.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Source words", total_words)
    k2.metric("Translated", f"{translated}/{len(st.session_state.segments)}")
    k3.metric("Approved", approved)
    k4.metric("QA flags", flagged)
    if not table.empty:
        st.dataframe(table[["#", "Words", "Status", "Effort", "Genre"]], use_container_width=True, hide_index=True)
    st.subheader("Search and replace")
    with st.form("search_replace_form"):
        search_text = st.text_input("Find in targets")
        replace_text = st.text_input("Replace with")
        replace_all = st.form_submit_button("Replace in all target segments")
    if replace_all and search_text:
        changed = 0
        for index, segment in enumerate(st.session_state.segments):
            new_target = segment.get("target", "").replace(search_text, replace_text)
            if new_target != segment.get("target", ""):
                record_revision(index, segment.get("target", ""), new_target, "search and replace")
                segment["target"] = new_target
                segment["edit_count"] = segment.get("edit_count", 0) + 1
                changed += 1
        st.success(f"Updated {changed} segment(s).")
    st.subheader("Delivery notes")
    st.session_state.delivery_notes = st.text_area("Client-facing delivery notes", st.session_state.delivery_notes, height=120)
    st.download_button("Download delivery package report", (f"Project: {st.session_state.project_name}\nClient: {st.session_state.client_name}\nLanguage pair: {st.session_state.language_pair}\nGenre: {st.session_state.genre}\nSource words: {total_words}\nTranslated segments: {translated}\nApproved segments: {approved}\nQA flags: {flagged}\n\nNotes:\n{st.session_state.delivery_notes}\n").encode("utf-8"), "delivery_report.txt", "text/plain")
