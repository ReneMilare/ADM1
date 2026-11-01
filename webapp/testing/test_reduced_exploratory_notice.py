from __future__ import annotations

from pathlib import Path

import pytest


NOTICE = "Modelo reduzido: exploratório, use para tendências, não para dimensionamento."


@pytest.mark.parametrize("page", ["01_Simular_Reator.py", "02_Comparar_Cenarios.py", "03_Design_de_Reator.py", "04_Validacao.py", "06_Configuracoes.py"])
def test_pages_show_reduced_exploratory_notice(page: str) -> None:
    source = (Path(__file__).parents[1] / "pages" / page).read_text(encoding="utf-8")
    assert NOTICE in source
