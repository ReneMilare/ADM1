from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from simulator.full_model.extension_registry import resolve_full_model_assembly
from simulator.full_model.governance import audit_governance_with_assembly
from simulator.full_model.solver import _clipping_diagnostics
from simulator.tests.test_extensions import _make_params, _run_extensions


def test_clipping_reports_segment_mass_and_minima():
    assembly = resolve_full_model_assembly([])
    n = len(assembly.dynamic_state_names)
    y = np.zeros((2 * n, 2))
    for segment in range(2):
        y[segment*n + assembly.dynamic_state_index['S_ac']] = [-0.001, -0.002]
        y[segment*n + assembly.dynamic_state_index['S_IN']] = [-0.001, 0]
        y[segment*n + assembly.dynamic_state_index['S_gas_ch4']] = [0, -0.003]
    params = dict(_make_params([]), V_liq=100.0, V_gas=10.0)
    report = _clipping_diagnostics(y, assembly, [params, params])
    assert report['minimum_negative_by_state']['S_ac'] == -0.002
    assert report['cod_kg_final'] == pytest.approx(0.46)
    assert report['cod_kg_max'] == pytest.approx(0.46)
    assert report['nitrogen_kg_max'] == pytest.approx(2.8)
    assert report['nitrogen_kg_final'] == 0


def test_lactate_stoichiometry_closes_cod_carbon_and_nitrogen():
    assembly = resolve_full_model_assembly(['lactate'])
    p = _make_params('lactate')
    row = {name: eval(expr, {'__builtins__': {}}, p) for name, expr in assembly.biochemical_stoichiometry_rows['rho_E6_uptake_lactate'].items()}
    assert row['S_bu'] == pytest.approx((1-p['Y_lac']) * .01 / .97)
    assert sum(row[k] for k in ('S_lac', 'S_ac', 'S_pro', 'S_bu', 'S_h2', 'X_lac')) == pytest.approx(0, abs=1e-12)
    carbon = sum(row[k] * p[c] for k, c in [('S_lac', 'C_lac'), ('S_ac', 'C_ac'), ('S_pro', 'C_pro'), ('S_bu', 'C_bu'), ('X_lac', 'C_bac')]) + row['S_IC']
    assert carbon == pytest.approx(0, abs=1e-12)
    assert row['S_IN'] + row['X_lac'] * p['N_bac'] == pytest.approx(0, abs=1e-12)


def test_governance_detects_missing_extension_source():
    assembly = resolve_full_model_assembly(['lactate'])
    params = tuple(replace(p, source='') if p.name == 'k_m_lac' else p for p in assembly.parameter_catalog)
    report = audit_governance_with_assembly(replace(assembly, parameter_catalog=params))
    assert 'k_m_lac' in report.parameters_without_source
    assert not report.all_checks_pass
    assert any(row.item == 'S_lac' and 'lactate_extension.py' in row.code_ref for row in report.traceability_rows)
    assert any(row.item == 'rho_E6_uptake_lactate' for row in report.traceability_rows)


def test_simulation_exposes_clipping_diagnostics():
    result = _run_extensions([], duration_days=0.2)
    report = result['metadata']['full_model_clipping']
    assert report['cod_kg_max'] >= report['cod_kg_final'] >= 0
    assert report['nitrogen_kg_max'] >= report['nitrogen_kg_final'] >= 0
    assert all(value < 0 for value in report['minimum_negative_by_state'].values())


def test_governance_detects_missing_extension_state_and_process_sources():
    assembly = resolve_full_model_assembly(['lactate'])
    states = tuple(replace(s, source='') if s.name == 'S_lac' else s for s in assembly.state_catalog)
    processes = tuple(replace(p, source='') if p.name == 'rho_E6_uptake_lactate' else p for p in assembly.process_catalog)
    report = audit_governance_with_assembly(replace(assembly, state_catalog=states, process_catalog=processes))
    assert report.states_without_source == ('S_lac',)
    assert report.processes_without_source == ('rho_E6_uptake_lactate',)
    assert not report.all_checks_pass
