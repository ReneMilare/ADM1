"""Seção: Painel de presets do usuário e gerenciamento de substratos personalizados."""
from __future__ import annotations

import streamlit as st

from webapp.components.tables import render_frame
from webapp.services.preferences_service import (
    delete_custom_substrate,
    delete_simulation_preset,
    list_custom_substrates,
    list_simulation_presets,
    save_custom_substrate,
    save_simulation_preset,
)
from webapp.services.simulation_service import (
    build_user_simulation_preset_payload,
    format_simulation_error,
)

_PENDING_PRESET_KEY = "sim_pending_preset_payload"


def render_preset_panel() -> None:
    """Renderiza o painel de presets do usuário e gerenciamento de substratos personalizados."""
    _render_user_presets()
    _render_save_preset()
    _render_custom_substrates()


def _render_user_presets() -> None:
    """Lista presets salvos com opções de aplicar e excluir."""
    saved_presets = list_simulation_presets()
    if not saved_presets:
        return

    with st.expander("Presets do usuário", expanded=False):
        preset_names = [str(item.get("name")) for item in saved_presets]
        selected_user_preset = st.selectbox(
            "Preset salvo",
            options=preset_names,
            key="user_simulation_preset",
        )
        preset_rows_user = []
        for item in saved_presets:
            summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
            preset_rows_user.append(
                {
                    "preset": item.get("name"),
                    "reator": summary.get("reactor_type"),
                    "modo": summary.get("substrate_mode"),
                    "substrato": summary.get("preset_id") or "manual",
                    "backend": summary.get("backend_choice"),
                    "duracao_d": summary.get("duration_days"),
                    "atualizado_em": item.get("updated_at"),
                }
            )
        render_frame(preset_rows_user)

        preset_col1, preset_col2 = st.columns(2)
        with preset_col1:
            if st.button("Aplicar preset salvo", width="stretch"):
                preset_payload = next(
                    item.get("payload")
                    for item in saved_presets
                    if str(item.get("name")) == selected_user_preset
                )
                queued_payload = dict(preset_payload)
                queued_payload["__pending_preset_name"] = selected_user_preset
                st.session_state[_PENDING_PRESET_KEY] = queued_payload
                st.rerun()
        with preset_col2:
            if st.button("Excluir preset salvo", width="stretch"):
                delete_simulation_preset(selected_user_preset)
                st.toast(f"Preset `{selected_user_preset}` excluído.")
                st.rerun()


def _render_save_preset() -> None:
    """Formulário para salvar o estado atual como novo preset."""
    with st.expander("Salvar preset do usuário", expanded=False):
        st.caption(
            "Salve a configuração atual para reutilizar o mesmo caso sem reconfigurar a tela manualmente."
        )
        preset_name = st.text_input("Nome do preset", key="save_user_preset_name")
        if st.button("Salvar configuração atual", width="stretch"):
            try:
                payload = build_user_simulation_preset_payload(st.session_state)
                save_simulation_preset(preset_name, payload)
                st.toast("Preset do usuário salvo com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(format_simulation_error(exc))


def _render_custom_substrates() -> None:
    """Gerenciamento de substratos personalizados."""
    with st.expander("Gerenciar substratos personalizados", expanded=False):
        st.caption(
            "Crie substratos personalizados reutilizáveis separados dos presets nativos. "
            "Cada substrato salvo pode ser selecionado no modo 'Personalizado'."
        )
        _saved_custom_list = list_custom_substrates()

        if _saved_custom_list:
            st.markdown("**Substratos salvos**")
            render_frame([
                {
                    "nome": item.get("name"),
                    "COD_part": f"{item.get('particulate_cod', 0):.2f}",
                    "COD_sol": f"{item.get('soluble_cod', 0):.2f}",
                    "pH": f"{item.get('ph', 0):.2f}",
                    "S_IC": f"{float(item.get('sic_kmol_m3', 0.0) or 0.0):.4f}" if item.get("sic_kmol_m3") not in (None, "", 0, 0.0) else "auto",
                    "atualizado": item.get("updated_at", ""),
                }
                for item in _saved_custom_list
            ])
            _del_name = st.selectbox(
                "Substrato para excluir",
                options=[item["name"] for item in _saved_custom_list],
                key="custom_substrate_to_delete",
            )
            if st.button("Excluir substrato selecionado", width="stretch"):
                delete_custom_substrate(_del_name)
                st.toast(f"Substrato '{_del_name}' excluído.")
                st.rerun()
        else:
            st.info("Nenhum substrato personalizado salvo ainda.")

        st.markdown("---")
        st.markdown("**Criar ou atualizar substrato personalizado**")
        _cs_col1, _cs_col2 = st.columns(2)
        with _cs_col1:
            _new_cs_name = st.text_input(
                "Nome do substrato",
                key="new_custom_substrate_name",
                placeholder="Ex: Lodo Misto Tratado",
            )
            _new_cs_pcod = st.number_input(
                "Particulate COD [kgCOD/m³]", min_value=0.0, value=8.0, step=0.5, key="new_cs_pcod"
            )
            _new_cs_scod = st.number_input(
                "Soluble COD [kgCOD/m³]", min_value=0.0, value=3.0, step=0.5, key="new_cs_scod"
            )
            _new_cs_ac = st.number_input(
                "Acetate [kgCOD/m³]", min_value=0.0, value=0.5, step=0.05, key="new_cs_ac"
            )
            _new_cs_pro = st.number_input(
                "Propionate [kgCOD/m³]", min_value=0.0, value=0.2, step=0.05, key="new_cs_pro"
            )
        with _cs_col2:
            _new_cs_h2 = st.number_input(
                "Hydrogen [kgCOD/m³]",
                min_value=0.0,
                value=0.001,
                step=0.001,
                format="%.4f",
                key="new_cs_h2",
            )
            _new_cs_nin = st.number_input(
                "Inorganic nitrogen [kgN/m³]", min_value=0.0, value=1.0, step=0.05, key="new_cs_nin"
            )
            _new_cs_alk = st.number_input(
                "Alkalinity proxy [escala legada]", min_value=0.01, value=4.0, step=0.1, key="new_cs_alk"
            )
            _new_cs_sic = st.number_input(
                "S_IC real [kmol/m³] (0 = derivar do proxy)", min_value=0.0, value=0.0, step=0.005, format="%.4f", key="new_cs_sic"
            )
            _new_cs_ph = st.number_input(
                "pH", min_value=5.0, max_value=8.5, value=7.0, step=0.05, key="new_cs_ph"
            )

        if st.button("Salvar substrato personalizado", width="stretch"):
            try:
                if not _new_cs_name or not _new_cs_name.strip():
                    st.error("Informe um nome para o substrato personalizado.")
                else:
                    save_custom_substrate(
                        _new_cs_name,
                        {
                            "particulate_cod": _new_cs_pcod,
                            "soluble_cod": _new_cs_scod,
                            "acetate": _new_cs_ac,
                            "propionate": _new_cs_pro,
                            "hydrogen": _new_cs_h2,
                            "inorganic_nitrogen": _new_cs_nin,
                            "alkalinity": _new_cs_alk,
                            "sic_kmol_m3": _new_cs_sic,
                            "ph": _new_cs_ph,
                        },
                    )
                    st.toast(f"Substrato personalizado '{_new_cs_name}' salvo.")
                    st.rerun()
            except Exception as exc:
                st.error(str(exc))
