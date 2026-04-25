"""Playwright screenshot capture para o README do ADM1 Workbench."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:8501"
OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1280, "height": 800}


def wait_streamlit(page: Page, extra: float = 1.5) -> None:
    try:
        page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=15000)
        page.wait_for_function(
            "document.readyState === 'complete'",
            timeout=10000,
        )
    except Exception:
        pass
    time.sleep(extra)


def hide_streamlit_toolbar(page: Page) -> None:
    """Remove toolbar de deploy e menu hamburger para screenshots mais limpas."""
    page.evaluate("""
        const toolbar = document.querySelector('[data-testid="stToolbar"]');
        if (toolbar) toolbar.style.display = 'none';
        const menu = document.querySelector('[data-testid="main-menu-button"]');
        if (menu) menu.style.display = 'none';
    """)


def scroll_and_capture(page: Page, path: Path, full_page: bool = True) -> None:
    hide_streamlit_toolbar(page)
    time.sleep(0.5)
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  Salvo: {path.name}")


def capture_home(page: Page) -> None:
    print("Capturando: Home")
    page.goto(BASE_URL, timeout=20000)
    wait_streamlit(page, extra=2.0)
    scroll_and_capture(page, OUT_DIR / "01_home.png")


def capture_simular_reator(page: Page) -> None:
    print("Capturando: Simular Reator — formulario")
    page.goto(f"{BASE_URL}/Simular_Reator", timeout=20000)
    wait_streamlit(page, extra=2.0)
    scroll_and_capture(page, OUT_DIR / "02_simular_reator_form.png", full_page=False)

    # Roda simulacao rapida com defaults e captura resultado
    print("  Rodando simulacao para capturar graficos...")
    try:
        # Clica no botao de simular (texto pode variar)
        run_btn = page.locator('button:has-text("Simular"), button:has-text("Rodar"), button:has-text("Executar")').first
        if run_btn.count() > 0:
            run_btn.click()
            # Aguarda spinner sumir e resultados aparecerem
            try:
                page.wait_for_selector('[data-testid="stSpinner"]', timeout=5000)
                page.wait_for_function(
                    "!document.querySelector('[data-testid=\"stSpinner\"]')",
                    timeout=60000,
                )
            except Exception:
                pass
            time.sleep(3.0)
            hide_streamlit_toolbar(page)
            page.screenshot(path=str(OUT_DIR / "03_simular_reator_resultado.png"), full_page=True)
            print(f"  Salvo: 03_simular_reator_resultado.png")

            # Scroll até gráficos Plotly e captura
            charts = page.locator('.js-plotly-plot')
            if charts.count() > 0:
                charts.first.scroll_into_view_if_needed()
                time.sleep(1.0)
                page.screenshot(path=str(OUT_DIR / "04_graficos_adm1.png"), full_page=False)
                print(f"  Salvo: 04_graficos_adm1.png")
    except Exception as exc:
        print(f"  Aviso: nao conseguiu rodar simulacao automaticamente — {exc}")


def capture_comparar_cenarios(page: Page) -> None:
    print("Capturando: Comparar Cenarios")
    page.goto(f"{BASE_URL}/Comparar_Cenarios", timeout=20000)
    wait_streamlit(page, extra=2.5)
    scroll_and_capture(page, OUT_DIR / "05_comparar_cenarios.png", full_page=False)

    # Captura graficos de sobreposicao se existirem
    charts = page.locator('.js-plotly-plot')
    if charts.count() > 0:
        print("  Graficos encontrados — capturando sobreposicao...")
        # Scroll até o primeiro gráfico
        charts.first.scroll_into_view_if_needed()
        time.sleep(1.5)
        hide_streamlit_toolbar(page)
        page.screenshot(path=str(OUT_DIR / "06_comparar_graficos.png"), full_page=False)
        print(f"  Salvo: 06_comparar_graficos.png")


def capture_design(page: Page) -> None:
    print("Capturando: Design de Reator")
    page.goto(f"{BASE_URL}/Design_de_Reator", timeout=20000)
    wait_streamlit(page, extra=2.0)
    scroll_and_capture(page, OUT_DIR / "07_design_de_reator.png", full_page=False)


def capture_validacao(page: Page) -> None:
    print("Capturando: Validacao")
    page.goto(f"{BASE_URL}/Validacao", timeout=20000)
    wait_streamlit(page, extra=2.0)
    scroll_and_capture(page, OUT_DIR / "08_validacao.png", full_page=False)


def capture_configuracoes(page: Page) -> None:
    print("Capturando: Configuracoes")
    page.goto(f"{BASE_URL}/Configuracoes", timeout=20000)
    wait_streamlit(page, extra=2.0)
    scroll_and_capture(page, OUT_DIR / "09_configuracoes.png", full_page=False)


def main() -> int:
    print(f"Salvando screenshots em: {OUT_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False para renderizar Plotly corretamente
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()

        capture_home(page)
        capture_simular_reator(page)
        capture_comparar_cenarios(page)
        capture_design(page)
        capture_validacao(page)
        capture_configuracoes(page)

        context.close()
        browser.close()

    saved = sorted(OUT_DIR.glob("*.png"))
    print(f"\nTotal: {len(saved)} screenshots salvos em {OUT_DIR}")
    for f in saved:
        size_kb = f.stat().st_size // 1024
        print(f"  {f.name} ({size_kb} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
