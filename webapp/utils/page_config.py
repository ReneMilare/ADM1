from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

_THEME_CSS_PATH = Path(__file__).resolve().parent / "theme.css"
_THEME_CSS = f"<style>\n{_THEME_CSS_PATH.read_text(encoding='utf-8')}\n</style>"


def configure_page(title: str) -> None:
    st.set_page_config(
        page_title=title,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def render_page_header(*, eyebrow: str, title: str, description: str) -> None:
    safe_eyebrow = html.escape(eyebrow)
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    st.markdown(
        f"""
        <div class=\"adm1-hero\">
          <div class=\"adm1-kicker\">{safe_eyebrow}</div>
          <h1>{safe_title}</h1>
          <p class=\"adm1-note\">{safe_description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_chip(label: str, status: str) -> str:
    css_class = {
        "ok": "adm1-chip adm1-chip-ok",
        "warning": "adm1-chip adm1-chip-warn",
        "error": "adm1-chip adm1-chip-error",
    }.get(status, "adm1-chip")
    return f"<span class=\"{css_class}\">{html.escape(label)}</span>"
