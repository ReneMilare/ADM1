"""Checklist de UX e verificação automatizada de restrições visuais.

Uso
---
    from webapp.testing.ux_checklist import check_ux_constraints, UX_CHECKLIST

    issues = check_ux_constraints(page_source_code)
    for issue in issues:
        print(issue)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Checklist humano — itens obrigatórios a serem revisados manualmente
# ---------------------------------------------------------------------------

UX_CHECKLIST: list[str] = [
    "Texto principal com contraste forte contra o fundo",
    "Proibido: fundo claro com letra clara",
    "Warnings, erros e fallback com destaque inequívoco",
    "Resultados e KPIs separados dos campos editáveis",
    "Estados de carregamento com st.spinner",
    "Blocos avançados dentro de st.expander",
    "Backend e fallback visíveis antes da execução",
]


# ---------------------------------------------------------------------------
# Estrutura de problema de UX detectado automaticamente
# ---------------------------------------------------------------------------

@dataclass
class UXIssue:
    rule: str
    severity: str  # "error" | "warning" | "info"
    line_number: int | None
    detail: str
    snippet: str = field(default="")

    def __str__(self) -> str:
        loc = f"linha {self.line_number}" if self.line_number else "local desconhecido"
        return f"[{self.severity.upper()}] {self.rule} ({loc}): {self.detail}"


# ---------------------------------------------------------------------------
# Regras de verificação automática
# ---------------------------------------------------------------------------

# Cores CSS consideradas "claras" (baixo contraste em fundo claro)
# Padrão: tons de cinza claro, amarelos suaves e brancos em #RRGGBB ou #RGB
_LIGHT_COLOR_PATTERN = re.compile(
    r"color\s*:\s*#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})\b",
)

# Limiares de luminância: componentes RGB > 0xCC em todos os canais = cor clara
_LIGHT_THRESHOLD = 0xCC


def _is_light_hex_color(hex_str: str) -> bool:
    """Retorna True se a cor hexadecimal for considerada clara (baixo contraste em fundo claro)."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    return r > _LIGHT_THRESHOLD and g > _LIGHT_THRESHOLD and b > _LIGHT_THRESHOLD


def _check_light_colors_in_markdown(lines: list[str]) -> list[UXIssue]:
    """Detecta uso de cores claras dentro de st.markdown com HTML."""
    issues: list[UXIssue]  = []
    in_markdown_block = False
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Detecta início de bloco st.markdown (simplificado, linha única)
        if "st.markdown" in stripped:
            in_markdown_block = True
        if in_markdown_block:
            for match in _LIGHT_COLOR_PATTERN.finditer(line):
                hex_color = match.group(1)
                if _is_light_hex_color(hex_color):
                    issues.append(
                        UXIssue(
                            rule="Contraste de cor",
                            severity="warning",
                            line_number=lineno,
                            detail=(
                                f"Cor clara #{hex_color} detectada em st.markdown. "
                                "Pode ter contraste insuficiente em fundo claro."
                            ),
                            snippet=stripped[:120],
                        )
                    )
        # Fecha o bloco quando a string parece terminada (heurística)
        if in_markdown_block and stripped.endswith('"""') or stripped.endswith("'''"):
            in_markdown_block = False
        elif in_markdown_block and stripped.endswith(")") and "st.markdown" not in stripped:
            in_markdown_block = False
    return issues


def _check_missing_error_widgets(lines: list[str]) -> list[UXIssue]:
    """Detecta estados de erro sem st.warning / st.error na mesma vizinhança."""
    issues: list[UXIssue] = []
    error_keywords = re.compile(r"\b(except|raise|Exception|Error|Traceback)\b")
    feedback_keywords = re.compile(r"st\.(warning|error|exception)\s*\(")

    window = 5  # linhas de contexto para procurar feedback
    for lineno, line in enumerate(lines, start=1):
        if error_keywords.search(line):
            start = max(0, lineno - 1 - window)
            end = min(len(lines), lineno + window)
            context = "\n".join(lines[start:end])
            if not feedback_keywords.search(context):
                issues.append(
                    UXIssue(
                        rule="Feedback de erro",
                        severity="warning",
                        line_number=lineno,
                        detail=(
                            "Tratamento de erro sem st.warning / st.error visível nas "
                            f"{window} linhas de contexto. O usuário pode não ser notificado."
                        ),
                        snippet=line.strip()[:120],
                    )
                )
    return issues


def _check_mixed_input_output(lines: list[str]) -> list[UXIssue]:
    """Detecta mistura de widgets de input e saída sem separadores visuais."""
    issues: list[UXIssue] = []
    input_pattern = re.compile(r"st\.(number_input|text_input|selectbox|slider|checkbox|radio|multiselect)\s*\(")
    output_pattern = re.compile(r"st\.(metric|dataframe|table|write|json|plotly_chart|pyplot)\s*\(")
    separator_pattern = re.compile(r"st\.(divider|subheader|header|markdown|expander)\s*\(")

    last_input_line: int | None = None
    last_separator_line: int | None = None

    for lineno, line in enumerate(lines, start=1):
        if input_pattern.search(line):
            last_input_line = lineno
        if separator_pattern.search(line):
            last_separator_line = lineno
        if output_pattern.search(line) and last_input_line is not None:
            # Se há output depois de input sem separador intermediário
            sep_between = (
                last_separator_line is not None
                and last_separator_line > last_input_line
                and last_separator_line < lineno
            )
            if not sep_between and (lineno - last_input_line) <= 10:
                issues.append(
                    UXIssue(
                        rule="Separação input/output",
                        severity="info",
                        line_number=lineno,
                        detail=(
                            f"Widget de resultado na linha {lineno} aparece próximo a widget "
                            f"de entrada (linha {last_input_line}) sem separador visual. "
                            "Considere usar st.divider() ou st.subheader() entre eles."
                        ),
                        snippet=line.strip()[:120],
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

def check_ux_constraints(page_source: str) -> list[UXIssue]:
    """Analisa o código-fonte de uma página Streamlit e retorna problemas de UX.

    Args:
        page_source: Conteúdo completo do arquivo .py da página Streamlit.

    Returns:
        Lista de :class:`UXIssue` ordenada por número de linha.
    """
    lines = page_source.splitlines()
    issues: list[UXIssue] = []
    issues.extend(_check_light_colors_in_markdown(lines))
    issues.extend(_check_missing_error_widgets(lines))
    issues.extend(_check_mixed_input_output(lines))
    issues.sort(key=lambda i: i.line_number or 0)
    return issues
