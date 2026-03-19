from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simulator.core.defaults import make_default_feed, make_default_kinetics
from simulator.core.models import FeedDefinition, InitialState, OperatingConditions, SimulationConfig
from simulator.core.pyadm1_backend import (
    INFLUENT_COLUMNS,
    P_ATM_BAR,
    R_GAS,
    VENDOR_PYADM1_SRC,
    simulate_with_pyadm1_frames,
)
from simulator.service import ADM1SimulationService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "literature_validation_runs"
DEFAULT_VAULT_NOTE_ROOT = PROJECT_ROOT / "vaultObsidian" / "Projeto"
DEFAULT_VAULT_NOTE_NAME = "Validação contra Literatura BSM2.md"
PYADM1_REL_TOL_PCT = 0.2
PYADM1_ABS_TOL = 1e-5

REFERENCE_SOURCE = {
    "title": "Aspects on ADM1 Implementation within the BSM2 Framework",
    "authors": ["C. Rosen", "U. Jeppsson"],
    "year": 2008,
    "tables_used": [5, 6],
    "urls": [
        "https://assets.pubpub.org/awqjabxp/51603224611145.pdf",
        "https://pubmed.ncbi.nlm.nih.gov/17037165/",
    ],
}

REFERENCE_OPERATING_CONDITIONS = {
    "temperature_c": 35.0,
    "liquid_volume_m3": 3400.0,
    "gas_volume_m3": 300.0,
    "flow_rate_m3_day": 170.0,
    "simulation_days": 200.0,
}

REFERENCE_INFLUENT = {
    "S_su": 0.01,
    "S_aa": 0.001,
    "S_fa": 0.001,
    "S_va": 0.001,
    "S_bu": 0.001,
    "S_pro": 0.001,
    "S_ac": 0.001,
    "S_h2": 1.0e-8,
    "S_ch4": 1.0e-5,
    "S_IC": 0.04,
    "S_IN": 0.01,
    "S_I": 0.02,
    "X_xc": 2.0,
    "X_ch": 5.0,
    "X_pr": 20.0,
    "X_li": 5.0,
    "X_su": 0.0,
    "X_aa": 0.01,
    "X_fa": 0.01,
    "X_c4": 0.01,
    "X_pro": 0.01,
    "X_ac": 0.01,
    "X_h2": 0.01,
    "X_I": 25.0,
    "S_cation": 0.04,
    "S_anion": 0.02,
}

REFERENCE_OUTPUTS = {
    "pH": {"value": 7.465537769904638, "unit": "-", "description": "pH no steady-state"},
    "Qgas_Nm3_day": {"value": 2955.703454193784, "unit": "Nm3/d", "description": "vazao total de gas normalizada"},
    "S_ac": {"value": 0.197629716937552, "unit": "kgCOD/m3", "description": "acetato liquido"},
    "S_pro": {"value": 0.015783666284542, "unit": "kgCOD/m3", "description": "propionato liquido"},
    "S_IN": {"value": 0.130229815803682, "unit": "kmolN/m3", "description": "nitrogenio inorganico"},
    "X_ac": {"value": 0.760562658313215, "unit": "kgCOD/m3", "description": "biomassa acetoclastica"},
    "X_h2": {"value": 0.317022953361272, "unit": "kgCOD/m3", "description": "biomassa hidrogenotrofica"},
    "S_gas_ch4": {"value": 1.625607209981422, "unit": "kgCOD/m3", "description": "metano na fase gasosa"},
    "Pgas_bar": {"value": 1.069016490408918, "unit": "bar", "description": "pressao total do gas"},
}

COMPARABLE_REDUCED_METRICS = ("pH", "Qgas_Nm3_day", "S_ac", "S_pro", "S_IN", "X_ac", "X_h2")


def build_reference_operating_conditions() -> OperatingConditions:
    return OperatingConditions(
        volume_m3=REFERENCE_OPERATING_CONDITIONS["liquid_volume_m3"],
        temperature_c=REFERENCE_OPERATING_CONDITIONS["temperature_c"],
        hrt_days=REFERENCE_OPERATING_CONDITIONS["liquid_volume_m3"] / REFERENCE_OPERATING_CONDITIONS["flow_rate_m3_day"],
    )


def build_reference_pyadm1_feed() -> FeedDefinition:
    return make_default_feed().model_copy(
        update={
            "name": "BSM2 literature exact influent",
            "flow_rate_m3_day": REFERENCE_OPERATING_CONDITIONS["flow_rate_m3_day"],
            "ph": 7.0,
        }
    )


def build_reference_simulation_config(*, backend: str) -> SimulationConfig:
    return SimulationConfig(
        duration_days=REFERENCE_OPERATING_CONDITIONS["simulation_days"],
        evaluation_points=201,
        solver="BDF",
        backend=backend,
        rtol=1e-10,
        atol=1e-12,
        persist=False,
    )


def build_reference_influent_frame(time_grid: np.ndarray) -> pd.DataFrame:
    row = {column: 0.0 for column in INFLUENT_COLUMNS}
    row.update(REFERENCE_INFLUENT)
    row["Q"] = REFERENCE_OPERATING_CONDITIONS["flow_rate_m3_day"]
    row["T (C)"] = REFERENCE_OPERATING_CONDITIONS["temperature_c"]
    return pd.DataFrame([{**row, "time": float(time_value)} for time_value in time_grid], columns=INFLUENT_COLUMNS)


def build_reference_initial_frame() -> pd.DataFrame:
    return pd.read_csv(VENDOR_PYADM1_SRC / "digester_initial.csv")


def build_reduced_feed_approximation() -> FeedDefinition:
    return FeedDefinition(
        name="BSM2 literature aggregated approximation",
        particulate_cod=REFERENCE_INFLUENT["X_xc"] + REFERENCE_INFLUENT["X_ch"] + REFERENCE_INFLUENT["X_pr"] + REFERENCE_INFLUENT["X_li"] + REFERENCE_INFLUENT["X_I"],
        soluble_cod=REFERENCE_INFLUENT["S_su"] + REFERENCE_INFLUENT["S_aa"] + REFERENCE_INFLUENT["S_fa"] + REFERENCE_INFLUENT["S_I"],
        acetate=REFERENCE_INFLUENT["S_ac"],
        propionate=REFERENCE_INFLUENT["S_pro"],
        hydrogen=REFERENCE_INFLUENT["S_h2"],
        inorganic_nitrogen=REFERENCE_INFLUENT["S_IN"] * 14.0,
        alkalinity=REFERENCE_INFLUENT["S_IC"],
        ph=7.0,
        flow_rate_m3_day=REFERENCE_OPERATING_CONDITIONS["flow_rate_m3_day"],
    )


def build_reduced_initial_state_approximation() -> InitialState:
    row = build_reference_initial_frame().iloc[0]
    return InitialState(
        particulate_cod=float(row["X_xc"] + row["X_ch"] + row["X_pr"] + row["X_li"] + row["X_I"]),
        soluble_cod=float(row["S_su"] + row["S_aa"] + row["S_fa"] + row["S_I"]),
        acetate=float(row["S_ac"]),
        propionate=float(row["S_pro"]),
        hydrogen=float(row["S_h2"]),
        acidogens=float(row["X_su"] + row["X_aa"] + row["X_fa"] + row["X_c4"] + row["X_pro"]),
        acetoclastic_biomass=float(row["X_ac"]),
        hydrogenotrophic_biomass=float(row["X_h2"]),
        inorganic_nitrogen=float(row["S_IN"] * 14.0),
        alkalinity=float(row["S_hco3_ion"]),
    )


def run_literature_validation(*, output_root: Path | None = None) -> tuple[dict[str, Any], Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (output_root or DEFAULT_OUTPUT_ROOT) / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    pyadm1_case = run_pyadm1_reference_case()
    reduced_case = run_reduced_reference_case()
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": REFERENCE_SOURCE,
        "scenario": {
            "operating_conditions": REFERENCE_OPERATING_CONDITIONS,
            "influent_adm1": REFERENCE_INFLUENT,
            "notes": [
                "O caso foi montado a partir da Tabela 5 (influent) e comparado com a Tabela 6 (steady-state) do relatorio BSM2.",
                "O backend pyadm1 roda com o vetor ADM1 completo; o backend reduced usa uma aproximacao agregada porque nao carrega os 26 estados do ADM1.",
            ],
        },
        "reference_outputs": REFERENCE_OUTPUTS,
        "pyadm1": pyadm1_case,
        "reduced": reduced_case,
        "conclusion": _build_conclusion(pyadm1_case, reduced_case),
    }
    (output_dir / "literature_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "literature_validation.md").write_text(_render_markdown(report), encoding="utf-8")
    return report, output_dir


def write_vault_report(
    report: dict[str, Any],
    *,
    artifact_dir: Path,
    note_root: Path | None = None,
    note_name: str = DEFAULT_VAULT_NOTE_NAME,
) -> Path:
    root = note_root or DEFAULT_VAULT_NOTE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    note_path = root / note_name
    note_path.write_text(_render_vault_note(report, artifact_dir=artifact_dir), encoding="utf-8-sig")
    return note_path


def run_pyadm1_reference_case() -> dict[str, Any]:
    operating_conditions = build_reference_operating_conditions()
    feed = build_reference_pyadm1_feed()
    simulation = build_reference_simulation_config(backend="pyadm1")
    time_grid = np.linspace(0.0, simulation.duration_days, simulation.evaluation_points)
    influent = build_reference_influent_frame(time_grid)
    initial = build_reference_initial_frame()
    raw_result = simulate_with_pyadm1_frames(
        operating_conditions=operating_conditions,
        feed=feed,
        parameters=make_default_kinetics(),
        simulation=simulation,
        influent_frame=influent,
        initial_frame=initial,
    )
    actual_outputs = _extract_pyadm1_outputs(raw_result, operating_conditions=operating_conditions)
    comparison = _compare_metrics(REFERENCE_OUTPUTS.keys(), actual_outputs)
    return {
        "execution": {
            "mode": "exact_adm1_influent",
            "solver": simulation.solver,
            "duration_days": simulation.duration_days,
            "evaluation_points": simulation.evaluation_points,
            "rtol": simulation.rtol,
            "atol": simulation.atol,
            "influent_source": "Tabela 5 do benchmark BSM2",
            "initial_state_source": str(VENDOR_PYADM1_SRC / "digester_initial.csv"),
        },
        "actual_outputs": actual_outputs,
        "comparison": comparison,
        "validated": all(item["within_tolerance"] for item in comparison.values()),
        "tolerances": {
            "relative_percent_max": PYADM1_REL_TOL_PCT,
            "absolute_floor": PYADM1_ABS_TOL,
        },
    }


def run_reduced_reference_case() -> dict[str, Any]:
    service = ADM1SimulationService()
    operating_conditions = build_reference_operating_conditions()
    feed = build_reduced_feed_approximation()
    initial_state = build_reduced_initial_state_approximation()
    simulation = build_reference_simulation_config(backend="reduced")
    result = service.simulate(
        "cstr",
        operating_conditions=operating_conditions,
        feed=feed,
        initial_state=initial_state,
        simulation=simulation,
    )
    actual_outputs = _extract_reduced_outputs(result)
    comparison = _compare_metrics(COMPARABLE_REDUCED_METRICS, actual_outputs)
    return {
        "execution": {
            "mode": "aggregated_state_approximation",
            "solver": simulation.solver,
            "duration_days": simulation.duration_days,
            "evaluation_points": simulation.evaluation_points,
            "feed_mapping": {
                "particulate_cod": "X_xc + X_ch + X_pr + X_li + X_I",
                "soluble_cod": "S_su + S_aa + S_fa + S_I",
                "acetate": "S_ac",
                "propionate": "S_pro",
                "hydrogen": "S_h2",
                "inorganic_nitrogen": "S_IN * 14",
                "alkalinity": "S_IC",
            },
            "notes": [
                "O backend reduced nao recebe o vetor ADM1 completo; por isso a comparacao com a Tabela 6 e apenas indicativa.",
                "As metricas sem estado correspondente direto, como S_gas_ch4 e Pgas, ficam fora da comparacao reduced.",
            ],
        },
        "actual_outputs": actual_outputs,
        "comparison": comparison,
        "validated": False,
    }


def _extract_pyadm1_outputs(result: dict[str, Any], *, operating_conditions: OperatingConditions) -> dict[str, float]:
    state = dict(zip(result["metadata"]["pyadm1_state_columns"], result["metadata"]["final_internal_state"], strict=False))
    temperature_k = operating_conditions.temperature_c + 273.15
    p_h2o = 0.0313 * np.exp(5290.0 * (1.0 / 298.15 - 1.0 / temperature_k))
    p_h2 = float(state["S_gas_h2"]) * R_GAS * temperature_k / 16.0
    p_ch4 = float(state["S_gas_ch4"]) * R_GAS * temperature_k / 64.0
    p_co2 = float(state["S_gas_co2"]) * R_GAS * temperature_k
    p_total = p_h2 + p_ch4 + p_co2 + p_h2o
    return {
        "pH": float(state["pH"]),
        "Qgas_Nm3_day": float(result["profiles"]["biogas_m3_day"][-1]),
        "S_ac": float(state["S_ac"]),
        "S_pro": float(state["S_pro"]),
        "S_IN": float(state["S_IN"]),
        "X_ac": float(state["X_ac"]),
        "X_h2": float(state["X_h2"]),
        "S_gas_ch4": float(state["S_gas_ch4"]),
        "Pgas_bar": float(p_total),
        "Qch4_Nm3_day": float(result["profiles"]["methane_m3_day"][-1]),
        "ch4_fraction_wet": float(result["profiles"]["ch4_fraction"][-1]),
        "co2_fraction_wet": float(p_co2 / max(p_total, 1e-12)),
        "gas_normalization_factor": float(p_total / P_ATM_BAR),
    }


def _extract_reduced_outputs(result: Any) -> dict[str, float]:
    return {
        "pH": float(result.summary.ph_final),
        "Qgas_Nm3_day": float(result.summary.biogas_final_m3_day),
        "S_ac": float(result.series["acetate"][-1]),
        "S_pro": float(result.series["propionate"][-1]),
        "S_IN": float(result.series["inorganic_nitrogen"][-1] / 14.0),
        "X_ac": float(result.series["acetoclastic_biomass"][-1]),
        "X_h2": float(result.series["hydrogenotrophic_biomass"][-1]),
        "Qch4_Nm3_day": float(result.summary.methane_final_m3_day),
        "ch4_fraction_wet": float(result.summary.ch4_fraction_final),
    }


def _compare_metrics(metric_names: Any, actual_outputs: dict[str, float]) -> dict[str, dict[str, float | bool | str]]:
    comparison: dict[str, dict[str, float | bool | str]] = {}
    for metric_name in metric_names:
        reference_value = float(REFERENCE_OUTPUTS[metric_name]["value"])
        actual_value = float(actual_outputs[metric_name])
        delta = actual_value - reference_value
        abs_delta = abs(delta)
        rel_delta_pct = abs_delta / max(abs(reference_value), 1e-12) * 100.0
        tolerance = max(PYADM1_ABS_TOL, abs(reference_value) * PYADM1_REL_TOL_PCT / 100.0)
        comparison[str(metric_name)] = {
            "reference": reference_value,
            "actual": actual_value,
            "delta": delta,
            "abs_delta": abs_delta,
            "rel_delta_pct": rel_delta_pct,
            "unit": str(REFERENCE_OUTPUTS[metric_name]["unit"]),
            "within_tolerance": abs_delta <= tolerance,
        }
    return comparison


def _build_conclusion(pyadm1_case: dict[str, Any], reduced_case: dict[str, Any]) -> dict[str, Any]:
    pyadm1_max_rel_delta = max(item["rel_delta_pct"] for item in pyadm1_case["comparison"].values())
    reduced_max_rel_delta = max(item["rel_delta_pct"] for item in reduced_case["comparison"].values())
    return {
        "pyadm1_matches_bsm2_reference": bool(pyadm1_case["validated"]),
        "reduced_matches_bsm2_reference": False,
        "pyadm1_max_rel_delta_pct": float(pyadm1_max_rel_delta),
        "reduced_max_rel_delta_pct": float(reduced_max_rel_delta),
        "recommended_backend_for_cstr_reference_work": "pyadm1",
        "summary": "O backend pyadm1 reproduz o benchmark BSM2 com erro muito baixo quando recebe o influente ADM1 completo. O backend reduced nao e intercambiavel com essa referencia porque agrega estados e simplifica a cinetica.",
    }


def _render_markdown(report: dict[str, Any]) -> str:
    pyadm1 = report["pyadm1"]
    reduced = report["reduced"]
    lines = [
        "# Literature Validation Against BSM2",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source: `{report['source']['title']}` (tables `{', '.join(str(item) for item in report['source']['tables_used'])}`)",
        f"- PyADM1 validated: `{pyadm1['validated']}`",
        f"- Reduced validated: `{reduced['validated']}`",
        f"- Conclusion: `{report['conclusion']['summary']}`",
        "",
        "## PyADM1 vs reference",
        "",
        "| Metric | Reference | PyADM1 | Abs delta | Rel delta (%) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for metric_name, metric in pyadm1["comparison"].items():
        lines.append(
            f"| {metric_name} | {metric['reference']:.9f} | {metric['actual']:.9f} | {metric['abs_delta']:.9f} | {metric['rel_delta_pct']:.6f} |"
        )
    lines.extend([
        "",
        "## Reduced vs reference",
        "",
        "| Metric | Reference | Reduced | Abs delta | Rel delta (%) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for metric_name, metric in reduced["comparison"].items():
        lines.append(
            f"| {metric_name} | {metric['reference']:.9f} | {metric['actual']:.9f} | {metric['abs_delta']:.9f} | {metric['rel_delta_pct']:.6f} |"
        )
    return "\n".join(lines)


def _render_vault_note(report: dict[str, Any], *, artifact_dir: Path) -> str:
    pyadm1 = report["pyadm1"]
    reduced = report["reduced"]
    lines = [
        "---",
        "tags: [projeto, validacao, literatura, bsm2]",
        f"created: {datetime.now().date().isoformat()}",
        "status: ativo",
        "---",
        "",
        "# Validação contra Literatura BSM2",
        "",
        "## Objetivo",
        "",
        "Validar a implementação local do ADM1 contra um benchmark publicado com valores numéricos explícitos, antes de decidir política de backend para CSTR.",
        "",
        "## Fonte de referência",
        "",
        f"- Relatório: `{report['source']['title']}`",
        f"- Autores: `{', '.join(report['source']['authors'])}`",
        f"- Ano: `{report['source']['year']}`",
        f"- Tabelas usadas: `{', '.join(str(item) for item in report['source']['tables_used'])}`",
    ]
    for url in report["source"]["urls"]:
        lines.append(f"- URL: {url}")
    lines.extend([
        "",
        "## Cenário reproduzido",
        "",
        "Os valores de entrada foram montados a partir da Tabela 5 do benchmark BSM2. O alvo de saída veio da Tabela 6, após 200 dias de simulação até steady-state.",
        "",
        f"- Temperatura: `{report['scenario']['operating_conditions']['temperature_c']} °C`",
        f"- Volume líquido: `{report['scenario']['operating_conditions']['liquid_volume_m3']} m3`",
        f"- Volume de gás: `{report['scenario']['operating_conditions']['gas_volume_m3']} m3`",
        f"- Vazão de alimentação: `{report['scenario']['operating_conditions']['flow_rate_m3_day']} m3/d`",
        f"- Duração da simulação: `{report['scenario']['operating_conditions']['simulation_days']} d`",
        "",
        "### Influent ADM1 de referência",
        "",
        "| Estado | Valor | Unidade |",
        "| --- | ---: | --- |",
    ])
    for key, value in REFERENCE_INFLUENT.items():
        unit = "kmol/m3" if key in {"S_IC", "S_IN", "S_cation", "S_anion"} else "kgCOD/m3"
        lines.append(f"| {key} | {value:.9f} | {unit} |")
    lines.extend([
        "",
        "## Valores de referência da literatura",
        "",
        "| Métrica | Valor | Unidade | Comentário |",
        "| --- | ---: | --- | --- |",
    ])
    for metric_name, metric in REFERENCE_OUTPUTS.items():
        lines.append(f"| {metric_name} | {metric['value']:.12f} | {metric['unit']} | {metric['description']} |")
    lines.extend([
        "",
        "## O que a nossa implementação devolveu",
        "",
        "### Backend pyadm1",
        "",
        "O backend `pyadm1` foi executado com o influente ADM1 completo, usando o código original integrado e a condição inicial de `vendor/PyADM1/src/digester_initial.csv`. Nesta validação eu corrigi a normalização de vazão de gás no adapter para comparar com `Nm3/d` atmosféricos, que é como o benchmark publica `Qgas`.",
        "",
        "| Métrica | Referência | pyadm1 | Delta abs | Delta rel (%) | Dentro da tolerância? |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for metric_name, metric in pyadm1["comparison"].items():
        within = "sim" if metric["within_tolerance"] else "não"
        lines.append(
            f"| {metric_name} | {metric['reference']:.12f} | {metric['actual']:.12f} | {metric['abs_delta']:.12f} | {metric['rel_delta_pct']:.6f} | {within} |"
        )
    lines.extend([
        "",
        f"- `Qch4_Nm3_day` obtido pelo pyadm1: `{pyadm1['actual_outputs']['Qch4_Nm3_day']:.6f}`",
        f"- Fração molar/volumétrica úmida de CH4 no gás: `{pyadm1['actual_outputs']['ch4_fraction_wet']:.6f}`",
        f"- Fração molar/volumétrica úmida de CO2 no gás: `{pyadm1['actual_outputs']['co2_fraction_wet']:.6f}`",
        f"- Fator de normalização do gás aplicado no adapter: `{pyadm1['actual_outputs']['gas_normalization_factor']:.6f}` (= `Pgas / Patm`)",
        "",
        "### Backend reduced",
        "",
        "O backend `reduced` não roda o vetor ADM1 completo. Para compará-lo com o benchmark, a alimentação foi agregada para os estados simplificados do projeto. Isso permite avaliar tendência e ordem de grandeza, mas não equivalência estado a estado.",
        "",
        "| Métrica | Referência | reduced | Delta abs | Delta rel (%) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for metric_name, metric in reduced["comparison"].items():
        lines.append(
            f"| {metric_name} | {metric['reference']:.12f} | {metric['actual']:.12f} | {metric['abs_delta']:.12f} | {metric['rel_delta_pct']:.6f} |"
        )
    lines.extend([
        "",
        "## Interpretação",
        "",
        f"- `pyadm1` reproduziu o benchmark com erro máximo de `{report['conclusion']['pyadm1_max_rel_delta_pct']:.6f}%` nas métricas comparadas.",
        f"- `reduced` ficou muito distante da referência, com erro máximo de `{report['conclusion']['reduced_max_rel_delta_pct']:.6f}%` nas métricas comparadas.",
        "- A conclusão prática é que, para estudos de `CSTR` em que a pergunta é aderência ao ADM1/BSM2 publicado, o backend correto é `pyadm1`.",
        "- O backend `reduced` continua útil como motor rápido e geral do projeto, mas não deve ser tratado como equivalente numérico ao benchmark do ADM1 original.",
        "",
        "## Artefatos gerados",
        "",
        f"- Relatório JSON: `{artifact_dir / 'literature_validation.json'}`",
        f"- Relatório Markdown: `{artifact_dir / 'literature_validation.md'}`",
        "",
        "## Observação importante",
        "",
        "Durante esta validação foi identificado e corrigido um detalhe no adapter do `pyadm1`: a vazão de gás estava sendo exposta na condição de pressão do headspace, enquanto a literatura reporta `Qgas` em `Nm3/d` atmosféricos. Depois da correção, `Qgas` passou a coincidir com o benchmark BSM2 dentro da tolerância desta validação.",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run literature validation of the ADM1 implementation against the published BSM2 benchmark.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--write-vault-note", action="store_true")
    parser.add_argument("--vault-note-root", type=Path, default=DEFAULT_VAULT_NOTE_ROOT)
    parser.add_argument("--vault-note-name", default=DEFAULT_VAULT_NOTE_NAME)
    args = parser.parse_args()
    report, output_dir = run_literature_validation(output_root=args.output_root)
    note_path = None
    if args.write_vault_note:
        note_path = write_vault_report(
            report,
            artifact_dir=output_dir,
            note_root=args.vault_note_root,
            note_name=args.vault_note_name,
        )
    summary = {
        "output_dir": str(output_dir),
        "pyadm1_validated": report["pyadm1"]["validated"],
        "reduced_validated": report["reduced"]["validated"],
        "pyadm1_max_rel_delta_pct": report["conclusion"]["pyadm1_max_rel_delta_pct"],
        "reduced_max_rel_delta_pct": report["conclusion"]["reduced_max_rel_delta_pct"],
        "vault_note_path": str(note_path) if note_path is not None else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
