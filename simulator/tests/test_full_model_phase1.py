from __future__ import annotations

from simulator.core.pyadm1_backend import INITIAL_COLUMNS, RESULT_COLUMNS
from simulator.full_model import (
    ACID_BASE_RELATIONS,
    ALGEBRAIC_STATE_NAMES,
    BIOCHEMICAL_PROCESS_NAMES,
    BIOCHEMICAL_STOICHIOMETRY_ROWS,
    CARBON_SIGMA_TERMS,
    DYNAMIC_STATE_NAMES,
    FULL_PARAMETER_CATALOG,
    FULL_PARAMETER_INDEX,
    FULL_PROCESS_CATALOG,
    FULL_STATE_CATALOG,
    FULL_STATE_NAMES,
    GAS_TRANSFER_RELATIONS,
    PSEUDO_STATE_NAMES,
    dense_biochemical_symbolic_matrix,
)
from simulator.full_model.mappings.pyadm1_names import PYADM1_RESULT_ORDER, PYADM1_STATE_ORDER


def test_state_catalog_matches_pyadm1_internal_order() -> None:
    assert FULL_STATE_NAMES == tuple(INITIAL_COLUMNS)
    assert FULL_STATE_NAMES == PYADM1_STATE_ORDER


def test_state_catalog_role_counts() -> None:
    assert len(FULL_STATE_CATALOG) == 38
    assert len(DYNAMIC_STATE_NAMES) == 29
    assert len(PSEUDO_STATE_NAMES) == 1
    assert len(ALGEBRAIC_STATE_NAMES) == 8


def test_result_order_matches_pyadm1_adapter() -> None:
    assert PYADM1_RESULT_ORDER == tuple(RESULT_COLUMNS)


def test_process_catalog_group_counts() -> None:
    biochemical = [process for process in FULL_PROCESS_CATALOG if process.family == "biochemical"]
    acid_base = [process for process in FULL_PROCESS_CATALOG if process.family == "acid_base"]
    gas_transfer = [process for process in FULL_PROCESS_CATALOG if process.family == "gas_transfer"]
    assert len(FULL_PROCESS_CATALOG) == 28
    assert len(biochemical) == 19
    assert len(acid_base) == 6
    assert len(gas_transfer) == 3


def test_parameter_catalog_contains_core_vendor_defaults() -> None:
    names = {parameter.name for parameter in FULL_PARAMETER_CATALOG}
    required = {"k_dis", "k_m_su", "K_S_h2", "K_a_ac", "k_L_a", "Y_h2", "C_bac", "N_bac"}
    assert required.issubset(names)
    assert len(FULL_PARAMETER_CATALOG) >= 100


def test_every_process_reference_uses_known_states_and_parameters() -> None:
    known_states = set(FULL_STATE_NAMES)
    known_parameters = set(FULL_PARAMETER_INDEX)
    for process in FULL_PROCESS_CATALOG:
        assert set(process.affected_states).issubset(known_states)
        assert set(process.parameters).issubset(known_parameters)


def test_biochemical_stoichiometry_rows_cover_every_biochemical_process() -> None:
    assert set(BIOCHEMICAL_STOICHIOMETRY_ROWS) == set(BIOCHEMICAL_PROCESS_NAMES)


def test_dense_biochemical_matrix_shape() -> None:
    state_names, process_names, matrix = dense_biochemical_symbolic_matrix()
    assert state_names == FULL_STATE_NAMES
    assert process_names == BIOCHEMICAL_PROCESS_NAMES
    assert len(matrix) == 19
    assert all(len(row) == len(FULL_STATE_NAMES) for row in matrix)


def test_carbon_sigma_terms_cover_biochemical_rows() -> None:
    assert tuple(CARBON_SIGMA_TERMS) == tuple(f"s_{index}" for index in range(1, 14))


def test_relation_catalogs_use_known_process_names() -> None:
    full_process_names = {process.name for process in FULL_PROCESS_CATALOG}
    assert set(ACID_BASE_RELATIONS).issubset(full_process_names)
    assert set(GAS_TRANSFER_RELATIONS).issubset(full_process_names)


def test_key_symbolic_rows_capture_expected_links() -> None:
    sugar = BIOCHEMICAL_STOICHIOMETRY_ROWS["rho_5_uptake_sugars"]
    acetate = BIOCHEMICAL_STOICHIOMETRY_ROWS["rho_11_uptake_acetate"]
    decay = BIOCHEMICAL_STOICHIOMETRY_ROWS["rho_13_decay_sugar_biomass"]
    assert sugar["S_su"] == "-1"
    assert sugar["X_su"] == "Y_su"
    assert sugar["S_h2"] == "(1 - Y_su) * f_h2_su"
    assert acetate["S_ch4"] == "1 - Y_ac"
    assert acetate["X_ac"] == "Y_ac"
    assert decay["X_xc"] == "1"
    assert decay["S_IC"] == "-s_13"


def test_internal_pseudo_states_expose_expected_aliases() -> None:
    alias_map = {state.name: state.result_alias for state in FULL_STATE_CATALOG if state.result_alias}
    assert alias_map == {"S_H_ion": "pH"}
