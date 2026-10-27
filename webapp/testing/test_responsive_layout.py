"""Playwright check: every page renders without errors and fits small viewports."""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = PROJECT_ROOT / "webapp" / "pages"
VIEWPORT_WIDTHS = (375, 768, 1280)
# Streamlit derives the URL path from the file name without the numeric prefix.
PAGE_PATHS = [""] + sorted(
    re.sub(r"^\d+_", "", path.stem) for path in PAGES_DIR.glob("[0-9][0-9]_*.py")
)

# Elements that overflow the viewport or still clip their text with an ellipsis.
LAYOUT_PROBE = """
() => {
  const vw = document.documentElement.clientWidth;
  const outside = [];
  for (const el of document.querySelectorAll('[data-testid="stMain"] *')) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (el.closest('[data-testid="stDataFrame"], pre, [data-testid="stCode"]')) continue;
    if (rect.right > vw + 2 && !outside.some((parent) => parent.contains(el))) {
      outside.push(el);
    }
  }
  const clipped = [...document.querySelectorAll(
    '[data-testid="stMetricLabel"] *, [data-testid="stMetricValue"], [data-testid="stMetricValue"] *, [data-testid="stMetricDelta"] *, [data-testid="stCheckbox"] label [data-testid="stMarkdownContainer"] *'
  )].filter((el) => (el.innerText || '').trim() && el.scrollWidth > el.clientWidth + 1);
  const label = (el) => `${el.tagName.toLowerCase()} "${(el.innerText || '').trim().slice(0, 50)}"`;
  return {
    pageScrollWidth: document.documentElement.scrollWidth,
    viewportWidth: vw,
    outside: outside.slice(0, 5).map(label),
    clipped: clipped.slice(0, 5).map(label),
    exceptions: [...document.querySelectorAll('[data-testid="stException"]')].map((el) => el.innerText.slice(0, 200)),
    sidebarExpanded: document.querySelector('[data-testid="stSidebar"]')?.getAttribute('aria-expanded') === 'true',
    autoNavPresent: !!document.querySelector('[data-testid="stSidebarNav"]'),
    navLabels: [...document.querySelectorAll('[data-testid="stSidebar"] [data-testid="stPageLink"] a')].map((a) => a.innerText.trim()),
  };
}
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "webapp" / "app.py"),
            "--server.headless", "true", "--server.port", str(port),
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://localhost:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(f"{url}/_stcore/health", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline or process.poll() is not None:
                pytest.fail("Streamlit did not become healthy within 60 s")
            time.sleep(1)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=20)


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    with sync_api.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch()
        except Exception as exc:  # browser binaries not installed
            pytest.skip(f"chromium is not available: {exc}")
        yield instance
        instance.close()


def _load(browser: object, url: str, width: int) -> dict:
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        page.goto(url, timeout=30_000)
        page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=30_000)
        # Wait until the script run finishes, then let late layout settle.
        page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60_000)
        page.wait_for_timeout(1500)
        return page.evaluate(LAYOUT_PROBE)
    finally:
        context.close()


@pytest.mark.parametrize("width", VIEWPORT_WIDTHS)
@pytest.mark.parametrize("page_path", PAGE_PATHS)
def test_page_renders_and_fits_viewport(base_url: str, browser: object, page_path: str, width: int) -> None:
    layout = _load(browser, f"{base_url}/{page_path}", width)

    assert layout["exceptions"] == [], f"page raised: {layout['exceptions']}"
    assert layout["pageScrollWidth"] <= layout["viewportWidth"] + 2, "page scrolls horizontally"
    assert layout["outside"] == [], f"elements overflow the viewport: {layout['outside']}"
    assert layout["clipped"] == [], f"text clipped with ellipsis: {layout['clipped']}"
    if width < 768:
        assert not layout["sidebarExpanded"], "sidebar covers the content on small screens"


def test_navigation_lists_only_user_pages(base_url: str, browser: object) -> None:
    layout = _load(browser, base_url, 1280)

    # Streamlit's file-based list showed "app" and "bootstrap"; the sidebar has its own links.
    assert not layout["autoNavPresent"]
    assert layout["navLabels"], "sidebar page links not found"
    lowered = [label.lower() for label in layout["navLabels"]]
    assert "bootstrap" not in lowered
    assert "app" not in lowered
