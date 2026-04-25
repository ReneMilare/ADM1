"""Playwright test: verifica que indicativos de fase (W1-W7) foram removidos de todas as paginas."""
from __future__ import annotations

import re
import sys
import time

from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:8501"

PHASE_PATTERN = re.compile(r"\bFases?\s+W\d|Camada\s+W\d|\bW[1-7]\b")

# URLs reais do Streamlit multipage (prefixo ~/)
PAGES = [
    ("Home", BASE_URL),
    ("Simular Reator", f"{BASE_URL}/Simular_Reator"),
    ("Comparar Cenarios", f"{BASE_URL}/Comparar_Cenarios"),
    ("Design de Reator", f"{BASE_URL}/Design_de_Reator"),
    ("Validacao", f"{BASE_URL}/Validacao"),
    ("Configuracoes", f"{BASE_URL}/Configuracoes"),
]


def wait_for_streamlit(page: Page) -> None:
    try:
        page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=15000)
        page.wait_for_function(
            "!document.querySelector('[data-testid=\"stStatusWidget\"]') || "
            "document.querySelector('[data-testid=\"stStatusWidget\"]').innerText.includes('Running') === false",
            timeout=12000,
        )
    except Exception:
        pass
    time.sleep(2.5)


def get_exception_text(page: Page) -> list[str]:
    texts = []
    try:
        exceptions = page.locator('[data-testid="stException"]').all()
        for exc in exceptions:
            texts.append(exc.inner_text()[:300])
    except Exception:
        pass
    return texts


def check_no_phase_indicators(page: Page, page_name: str) -> list[str]:
    failures: list[str] = []
    try:
        body_text = page.locator("body").inner_text()
        matches = PHASE_PATTERN.findall(body_text)
        for match in matches:
            failures.append(f"[{page_name}] Indicativo de fase encontrado: '{match}'")
    except Exception as exc:
        failures.append(f"[{page_name}] Erro ao ler texto da pagina: {exc}")
    return failures


def check_page_loaded(page: Page, page_name: str) -> list[str]:
    failures: list[str] = []
    exception_texts = get_exception_text(page)
    if exception_texts:
        for t in exception_texts:
            failures.append(f"[{page_name}] Streamlit exception: {t[:200]}")
    return failures


def run_tests() -> int:
    all_failures: list[str] = []
    results: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        for page_name, url in PAGES:
            print(f"  Testando: {page_name} ({url})")
            try:
                page.goto(url, timeout=20000)
                wait_for_streamlit(page)

                load_failures = check_page_loaded(page, page_name)
                phase_failures = check_no_phase_indicators(page, page_name)

                page_failures = load_failures + phase_failures
                if page_failures:
                    all_failures.extend(page_failures)
                    results.append((page_name, "FAIL"))
                else:
                    results.append((page_name, "PASS"))
            except Exception as exc:
                all_failures.append(f"[{page_name}] Erro ao carregar pagina: {exc}")
                results.append((page_name, "ERROR"))

        context.close()
        browser.close()

    print()
    print("=" * 60)
    print("RESULTADO")
    print("=" * 60)
    for name, status in results:
        icon = "OK" if status == "PASS" else "XX"
        print(f"  {icon} {name:30s} {status}")
    print()

    if all_failures:
        print("FALHAS:")
        for f in all_failures:
            # encode safe para cp1252
            safe = f.encode("ascii", errors="replace").decode("ascii")
            print(f"  - {safe}")
        return 1

    print("Todos os testes passaram. Nenhum indicativo de fase encontrado.")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
