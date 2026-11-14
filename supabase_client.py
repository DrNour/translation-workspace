import os

import requests


def _raise_with_message(response):
    if response.ok:
        return
    try:
        details = response.json()
        message = details.get("msg") or details.get("message") or details.get("error_description") or details.get("error")
    except ValueError:
        message = response.text.strip()
    raise RuntimeError(f"Supabase authentication error ({response.status_code}): {message or 'request rejected'}")


def config():
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
    except Exception:
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    return (url or "").rstrip("/"), key or ""


def configured():
    url, key = config()
    return bool(url and key)


def sign_in(email, password):
    url, key = config()
    response = requests.post(
        f"{url}/auth/v1/token?grant_type=password",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    _raise_with_message(response)
    return response.json()


def sign_up(email, password):
    url, key = config()
    response = requests.post(
        f"{url}/auth/v1/signup",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    _raise_with_message(response)
    return response.json()


def reset_password(email):
    url, key = config()
    response = requests.post(
        f"{url}/auth/v1/recover",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"email": email},
        timeout=20,
    )
    _raise_with_message(response)
    return response.json() if response.content else {}


def refresh_session(refresh_token):
    url, key = config()
    response = requests.post(
        f"{url}/auth/v1/token?grant_type=refresh_token",
        headers={"apikey": key, "Content-Type": "application/json"},
        json={"refresh_token": refresh_token},
        timeout=20,
    )
    _raise_with_message(response)
    return response.json()


def save_project(access_token, project_name, payload):
    url, key = config()
    response = requests.post(
        f"{url}/rest/v1/projects",
        headers={"apikey": key, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=representation"},
        json={"name": project_name, "payload": payload},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def latest_project(access_token):
    url, key = config()
    response = requests.get(
        f"{url}/rest/v1/projects?select=name,payload,updated_at&order=updated_at.desc&limit=1",
        headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def create_workspace(access_token, name):
    url, key = config()
    headers = {"apikey": key, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "Prefer": "return=representation"}
    response = requests.post(f"{url}/rest/v1/workspaces", headers=headers, json={"name": name}, timeout=30)
    response.raise_for_status()
    workspace = response.json()[0]
    requests.post(f"{url}/rest/v1/workspace_members", headers=headers, json={"workspace_id": workspace["id"], "user_id": workspace["owner_id"], "role": "owner"}, timeout=30).raise_for_status()
    return workspace


def list_workspaces(access_token):
    url, key = config()
    response = requests.get(f"{url}/rest/v1/workspaces?select=id,name,owner_id,created_at&order=created_at.desc", headers={"apikey": key, "Authorization": f"Bearer {access_token}"}, timeout=30)
    response.raise_for_status()
    return response.json()


def create_invitation(access_token, workspace_id, email, role):
    url, key = config()
    response = requests.post(
        f"{url}/rest/v1/workspace_invitations",
        headers={"apikey": key, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json", "Prefer": "return=representation"},
        json={"workspace_id": workspace_id, "email": email.lower().strip(), "role": role},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()[0]
