from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

_THEME_CSS_PATH = Path(__file__).resolve().parent / "theme.css"


def configure_page(title: str) -> None:
    st.set_page_config(
        page_title=title,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _theme_css = f"<style>\n{_THEME_CSS_PATH.read_text(encoding='utf-8')}\n</style>"
    st.markdown(_theme_css, unsafe_allow_html=True)


def render_page_header(*, title: str, description: str, eyebrow: str | None = None) -> None:
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    kicker_html = f'<div class="adm1-kicker">{html.escape(eyebrow)}</div>' if eyebrow else ""
    st.markdown(
        f"""
        <div class=\"adm1-hero\">
          {kicker_html}
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
