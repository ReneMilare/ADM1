"""Seção: Configuração de substrato — preset, co-digestão, personalizado, manual."""
from __future__ import annotations

import streamlit as st

from webapp.components.tables import render_frame
from webapp.services.preferences_service import find_custom_substrate, list_custom_substrates
from webapp.utils.presets import (
    CODIGESTION_PRESET_LABELS,
    get_codigestion_blend,
    get_manual_defaults,
    get_preset_bundle,
    get_substrate_options,
    preset_rows,
)


def render_substrate_config() -> None:
    """Renderiza o seletor e configuração de substrato com base em sim_substrate_mode."""
    substrate_mode = st.session_state.get("sim_substrate_mode", "preset")
    ui_mode = st.session_state.get("sim_ui_mode", "operador")

    substrate_options = get_substrate_options()
    single_substrate_options = {k: v for k, v in substrate_options.items() if k not in CODIGESTION_PRESET_LABELS}
    codigestion_options = {k: v for k, v in substrate_options.items() if k in CODIGESTION_PRESET_LABELS}

    preset_id: str | None = None
    preset_link: str | None = None
    base_feed = None
    base_operating = None

    if substrate_mode == "preset":
        # Garantir que o valor inicial da chave seja um preset válido
        if st.session_state.get("sim_preset_id") not in single_substrate_options and single_substrate_options:
            st.session_state["sim_preset_id"] = next(iter(single_substrate_options))
        preset_id = st.selectbox(
            "Preset de substrato",
            options=list(single_substrate_options),
            format_func=lambda v: single_substrate_options[v],
            key="sim_preset_id",
        )
        if preset_id is None:
            preset_id = next(iter(single_substrate_options))
        base_feed, base_operating, preset_link = get_preset_bundle(preset_id)
        st.caption(
            f"Preset: **{single_substrate_options.get(preset_id, preset_id)}** | "
            f"COD part: {base_feed.particulate_cod:.3f} | "
            f"pH: {base_feed.ph:.2f} | "
            f"HRT ref: {base_operating.hrt_days:.1f} d"
        )

    elif substrate_mode == "codigestion":
        _CUSTOM_KEY = "__custom__"
        all_codig_options = {**codigestion_options, _CUSTOM_KEY: "Personalizado (escolher substratos e frações)"}
        codig_preset_id = st.selectbox(
            "Preset de co-digestão",
            options=list(all_codig_options),
            format_func=lambda v: all_codig_options[v],
            key="codigestion_preset",
        )

        if codig_preset_id == _CUSTOM_KEY:
            preset_id = None
            selected_substrates = st.multiselect(
                "Substratos a combinar",
                options=list(single_substrate_options),
                default=list(single_substrate_options)[:2],
                format_func=lambda v: single_substrate_options[v],
                key="codig_custom_substrates",
            )
            if len(selected_substrates) < 2:
                st.warning("Selecione pelo menos 2 substratos para a co-digestão.")
                base_feed, base_operating = get_manual_defaults()
                preset_link = None
            else:
                frac_cols = st.columns(len(selected_substrates))
                raw_fractions: dict[str, float] = {}
                for i, sub_id in enumerate(selected_substrates):
                    default_frac = round(1.0 / len(selected_substrates), 2)
                    raw_fractions[sub_id] = frac_cols[i].number_input(
                        single_substrate_options[sub_id],
                        min_value=0.01,
                        max_value=0.99,
                        value=float(st.session_state.get(f"codig_frac_{sub_id}", default_frac)),
                        step=0.05,
                        format="%.2f",
                        key=f"codig_frac_{sub_id}",
                    )
                total_frac = sum(raw_fractions.values())
                st.caption(f"Soma das frações: **{total_frac:.2f}** (deve ser 1,00)")
                if abs(total_frac - 1.0) > 0.005:
                    st.error(f"⚠️ As frações somam {total_frac:.2f} — ajuste para que somem 1,00.")
                    base_feed, base_operating = get_manual_defaults()
                    preset_link = None
                else:
                    from simulator.core.models import CoDigestionBlend as _CDB, SubstrateFraction as _SF
                    _components = []
                    for sub_id, frac in raw_fractions.items():
                        sub_feed, sub_op, _ = get_preset_bundle(sub_id)
                        _components.append(_SF(feed=sub_feed, volume_fraction=round(frac / total_frac, 6)))
                    _blend_name = " + ".join(
                        f"{single_substrate_options[s][:12]} {raw_fractions[s]:.0%}"
                        for s in selected_substrates
                    )
                    _blend = _CDB(name=_blend_name, components=_components)
                    base_feed = _blend.blend()
                    _dominant = max(raw_fractions, key=lambda k: raw_fractions[k])
                    _, base_operating, _ = get_preset_bundle(_dominant)
                    preset_link = None
                    cn = _blend.cn_ratio()
                    st.caption(
                        f"Blended feed: {base_feed.name} | "
                        f"Frações: {', '.join(f'{c.feed.name} {c.volume_fraction:.0%}' for c in _blend.components)} | "
                        f"C/N estimado: {cn:.1f}"
                    )
                    st.info("💡 Co-digestão ativa: recomenda-se o modo `fan` de inibição por amônia.")
        else:
            preset_id = codig_preset_id
            codigestion_blend = get_codigestion_blend(codig_preset_id) if codig_preset_id else None
            if codigestion_blend is not None:
                base_feed = codigestion_blend.blend()
                from simulator.design_pipeline import CODIGESTION_PRESETS
                _cpdata = CODIGESTION_PRESETS.get(codig_preset_id, {})
                base_operating = _cpdata.get("operating", None)
                if base_operating is None:
                    _, base_operating = get_manual_defaults()
                preset_link = str(_cpdata.get("note_link", codigestion_options.get(codig_preset_id, "")))
                cn = codigestion_blend.cn_ratio()
                st.caption(
                    f"Componentes: {', '.join(c.feed.name for c in codigestion_blend.components)} | "
                    f"Frações: {', '.join(f'{c.volume_fraction:.0%}' for c in codigestion_blend.components)} | "
                    f"C/N estimado: {cn:.1f}"
                )
                st.info("💡 Co-digestão ativa: recomenda-se o modo `fan` de inibição por amônia para resultados mais realistas.")
            else:
                base_feed, base_operating = get_manual_defaults()
                preset_link = None

    elif substrate_mode == "custom":
        saved_substrates = list_custom_substrates()
        if not saved_substrates:
            st.warning(
                "Nenhum substrato personalizado salvo. "
                "Use o painel 'Gerenciar substratos personalizados' para criar um."
            )
            base_feed, base_operating = get_manual_defaults()
            preset_id = None
            preset_link = None
        else:
            custom_substrate_opts = {str(item["name"]): str(item["name"]) for item in saved_substrates}
            _prev_custom = st.session_state.get("sim_custom_substrate_name")
            _custom_default = (
                _prev_custom if _prev_custom in custom_substrate_opts else next(iter(custom_substrate_opts))
            )
            selected_custom_name = st.selectbox(
                "Substrato personalizado",
                options=list(custom_substrate_opts),
                format_func=lambda v: custom_substrate_opts[v],
                index=list(custom_substrate_opts).index(_custom_default)
                if _custom_default in custom_substrate_opts
                else 0,
                key="sim_custom_substrate_name",
            )
            _custom_data = find_custom_substrate(selected_custom_name) or {}
            base_feed, base_operating = get_manual_defaults()
            base_feed = base_feed.model_copy(
                update={
                    "name": str(_custom_data.get("name", selected_custom_name)),
                    "particulate_cod": float(_custom_data.get("particulate_cod", base_feed.particulate_cod)),
                    "soluble_cod": float(_custom_data.get("soluble_cod", base_feed.soluble_cod)),
                    "acetate": float(_custom_data.get("acetate", base_feed.acetate)),
                    "propionate": float(_custom_data.get("propionate", base_feed.propionate)),
                    "hydrogen": float(_custom_data.get("hydrogen", base_feed.hydrogen)),
                    "inorganic_nitrogen": float(
                        _custom_data.get("inorganic_nitrogen", base_feed.inorganic_nitrogen)
                    ),
                    "alkalinity": float(_custom_data.get("alkalinity", base_feed.alkalinity)),
                    "sic_kmol_m3": (
                        float(_custom_data["sic_kmol_m3"])
                        if _custom_data.get("sic_kmol_m3") not in (None, "", 0, 0.0)
                        else base_feed.sic_kmol_m3
                    ),
                    "ph": float(_custom_data.get("ph", base_feed.ph)),
                }
            )
            preset_id = None
            preset_link = None
            st.caption(
                f"Substrato: **{selected_custom_name}** | "
                f"COD part: {_custom_data.get('particulate_cod', 0):.2f} | "
                f"COD sol: {_custom_data.get('soluble_cod', 0):.2f} | "
                f"pH: {_custom_data.get('ph', 0):.2f} | "
                f"Atualizado: {_custom_data.get('updated_at', 'N/A')}"
            )

    else:  # manual
        base_feed, base_operating = get_manual_defaults()
        preset_link = None

    # ── Base reset logic ────────────────────────────────────────────────────────
    source_signature = (
        f"{substrate_mode}:{preset_id or st.session_state.get('sim_custom_substrate_name') or 'manual'}"
    )
    skip_base_reset = bool(st.session_state.pop("sim_skip_base_reset", False))
    if st.session_state.get("sim_base_signature") != source_signature and not skip_base_reset:
        if base_operating is not None:
            st.session_state["volume_active"] = float(base_operating.volume_m3)
            st.session_state["temperature_active"] = float(base_operating.temperature_c)
            st.session_state["hrt_active"] = float(base_operating.hrt_days)
        if substrate_mode == "manual" and base_feed is not None:
            st.session_state["manual_feed_name"] = base_feed.name
            st.session_state["manual_particulate_cod"] = float(base_feed.particulate_cod)
            st.session_state["manual_soluble_cod"] = float(base_feed.soluble_cod)
            st.session_state["manual_acetate"] = float(base_feed.acetate)
            st.session_state["manual_propionate"] = float(base_feed.propionate)
            st.session_state["manual_hydrogen"] = float(base_feed.hydrogen)
            st.session_state["manual_inorganic_nitrogen"] = float(base_feed.inorganic_nitrogen)
            st.session_state["manual_alkalinity"] = float(base_feed.alkalinity)
            st.session_state["manual_sic_kmol_m3"] = float(base_feed.sic_kmol_m3 or 0.0)
            st.session_state["manual_feed_ph"] = float(base_feed.ph)
        st.session_state["sim_base_signature"] = source_signature

    # ── Manual feed fields ──────────────────────────────────────────────────────
    if substrate_mode == "manual":
        st.divider()
        st.markdown("**Composição da alimentação (manual)**")
        st.caption("Separe o proxy legado de alcalinidade do carbono inorgânico real `S_IC` quando estiver usando `full` ou `pyadm1`.")
        _mf_left, _mf_right = st.columns(2)
        _defaults = base_feed if base_feed is not None else get_manual_defaults()[0]
        with _mf_left:
            st.text_input(
                "Nome da alimentação",
                value=st.session_state.get("manual_feed_name", _defaults.name),
                key="manual_feed_name",
            )
            st.number_input(
                "Particulate COD [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_particulate_cod", _defaults.particulate_cod)),
                step=0.1,
                key="manual_particulate_cod",
            )
            st.number_input(
                "Soluble COD [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_soluble_cod", _defaults.soluble_cod)),
                step=0.1,
                key="manual_soluble_cod",
            )
            st.number_input(
                "Acetate [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_acetate", _defaults.acetate)),
                step=0.05,
                key="manual_acetate",
            )
            st.number_input(
                "Propionate [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_propionate", _defaults.propionate)),
                step=0.05,
                key="manual_propionate",
            )
        with _mf_right:
            st.number_input(
                "Hydrogen [kgCOD/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_hydrogen", _defaults.hydrogen)),
                step=0.001,
                format="%.4f",
                key="manual_hydrogen",
            )
            st.number_input(
                "Inorganic nitrogen [kgN/m³]",
                min_value=0.0,
                value=float(st.session_state.get("manual_inorganic_nitrogen", _defaults.inorganic_nitrogen)),
                step=0.05,
                key="manual_inorganic_nitrogen",
            )
            st.number_input(
                "Alkalinity proxy [escala legada]",
                min_value=0.1,
                value=float(st.session_state.get("manual_alkalinity", _defaults.alkalinity)),
                step=0.05,
                key="manual_alkalinity",
                help="Usado pelo backend reduced e como fallback legado quando S_IC real não for informado.",
            )
            st.number_input(
                "S_IC real [kmol/m³] (0 = derivar do proxy)",
                min_value=0.0,
                value=float(st.session_state.get("manual_sic_kmol_m3", _defaults.sic_kmol_m3 or 0.0)),
                step=0.005,
                format="%.4f",
                key="manual_sic_kmol_m3",
                help="Entrada física de carbono inorgânico dissolvido usada pelo ADM1 full e pelo PyADM1.",
            )
            st.number_input(
                "Influent pH",
                min_value=5.0,
                max_value=8.5,
                value=float(st.session_state.get("manual_feed_ph", _defaults.ph)),
                step=0.05,
                key="manual_feed_ph",
            )

    elif substrate_mode == "custom":
        if ui_mode == "especialista" and base_feed is not None:
            with st.expander("Parâmetros do substrato personalizado", expanded=False):
                render_frame([
                    {"parametro": "Feed", "valor": base_feed.name},
                    {"parametro": "Particulate COD", "valor": f"{base_feed.particulate_cod:.3f} kgCOD/m³"},
                    {"parametro": "Soluble COD", "valor": f"{base_feed.soluble_cod:.3f} kgCOD/m³"},
                    {"parametro": "Acetate", "valor": f"{base_feed.acetate:.3f} kgCOD/m³"},
                    {"parametro": "Propionate", "valor": f"{base_feed.propionate:.3f} kgCOD/m³"},
                    {"parametro": "Influent pH", "valor": f"{base_feed.ph:.2f}"},
                    {"parametro": "Inorganic N", "valor": f"{base_feed.inorganic_nitrogen:.3f} kgN/m³"},
                    {"parametro": "Alkalinity proxy", "valor": f"{base_feed.alkalinity:.3f} escala legada"},
                    {"parametro": "S_IC real", "valor": f"{base_feed.sic_kmol_m3:.4f} kmol/m³" if base_feed.sic_kmol_m3 is not None else "derivado do proxy"},
                ])

    elif substrate_mode == "preset":
        if ui_mode == "especialista" and base_feed is not None:
            with st.expander("Composição do preset", expanded=False):
                render_frame(preset_rows())

    # ── ASM1→ADM1 interface ─────────────────────────────────────────────────────
    if ui_mode == "especialista" or "asm1_adm1_influent" in st.session_state:
        _render_asm1_interface()

    # ── Composition → ADM1 converter ────────────────────────────────────────────
    _render_composition_converter()


def _render_asm1_interface() -> None:
    """Renderiza o painel de conversão ASM1→ADM1 (Interface E14/BSM2)."""
    with st.expander("🔄 Converter influente ASM1 → ADM1 (Interface E14 / BSM2)", expanded=False):
        st.caption(
            "Use se o afluente do digestor vem de um sistema de lodos ativados (ASM1). "
            "Converte variáveis ASM1 para influente ADM1 seguindo a interface BSM2 (Nopens et al. 2009)."
        )
        _a1_col1, _a1_col2, _a1_col3, _a1_col4 = st.columns(4)
        _a1_S_S = _a1_col1.number_input("S_S [gCOD/m³]", 0.0, 50000.0, 100.0, key="a1_S_S")
        _a1_S_I = _a1_col2.number_input("S_I [gCOD/m³]", 0.0, 20000.0, 30.0, key="a1_S_I")
        _a1_X_S = _a1_col3.number_input("X_S [gCOD/m³]", 0.0, 50000.0, 200.0, key="a1_X_S")
        _a1_X_I = _a1_col4.number_input("X_I [gCOD/m³]", 0.0, 20000.0, 50.0, key="a1_X_I")

        _a1_col5, _a1_col6, _a1_col7 = st.columns(3)
        _a1_X_BH = _a1_col5.number_input("X_BH [gCOD/m³]", 0.0, 50000.0, 300.0, key="a1_X_BH")
        _a1_X_BA = _a1_col6.number_input("X_BA [gCOD/m³]", 0.0, 10000.0, 40.0, key="a1_X_BA")
        _a1_X_P = _a1_col7.number_input("X_P [gCOD/m³]", 0.0, 20000.0, 80.0, key="a1_X_P")

        _a1_col8, _a1_col9, _a1_col10, _a1_col11, _a1_col12 = st.columns(5)
        _a1_S_ND = _a1_col8.number_input("S_ND [gN/m³]", 0.0, 500.0, 2.0, key="a1_S_ND")
        _a1_X_ND = _a1_col9.number_input("X_ND [gN/m³]", 0.0, 500.0, 4.0, key="a1_X_ND")
        _a1_S_NH = _a1_col10.number_input("S_NH [gN/m³]", 0.0, 1000.0, 20.0, key="a1_S_NH")
        _a1_S_NO = _a1_col11.number_input("S_NO [gN/m³]", 0.0, 500.0, 5.0, key="a1_S_NO")
        _a1_S_ALK = _a1_col12.number_input("S_ALK [molHCO₃⁻/m³]", 0.0, 100.0, 4.0, key="a1_S_ALK")

        _a1_preset = st.selectbox(
            "Preset de frações BSM2",
            options=["BSM2 (lodo misto municipal)", "Lodo primário", "Lodo secundário aeróbio"],
            key="a1_fractions_preset",
        )

        if st.button("▶ Calcular influente ADM1", key="a1_calculate"):
            from simulator.full_model.asm_adm1_interface import (
                ASM1State,
                asm1_to_adm1_influent,
                verify_asm1_adm1_balance,
            )
            from simulator.full_model.mappings.asm1_fractions import (
                bsm2_fractions,
                primary_sludge_fractions,
                secondary_sludge_fractions,
            )
            _preset_map = {
                "BSM2 (lodo misto municipal)": bsm2_fractions(),
                "Lodo primário": primary_sludge_fractions(),
                "Lodo secundário aeróbio": secondary_sludge_fractions(),
            }
            _fracs = _preset_map[_a1_preset]
            _asm1 = ASM1State(
                S_S=_a1_S_S, S_I=_a1_S_I, X_S=_a1_X_S, X_I=_a1_X_I,
                X_BH=_a1_X_BH, X_BA=_a1_X_BA, X_P=_a1_X_P,
                S_ND=_a1_S_ND, X_ND=_a1_X_ND, S_NH=_a1_S_NH,
                S_NO=_a1_S_NO, S_ALK=_a1_S_ALK,
            )
            _influent = asm1_to_adm1_influent(_asm1, _fracs)
            _balance = verify_asm1_adm1_balance(_asm1, _influent)
            st.session_state["asm1_adm1_influent"] = _influent
            st.session_state["asm1_adm1_balance"] = _balance
            _result_rows = [
                {
                    "Estado ADM1": k,
                    "Valor": f"{v:.6f}",
                    "Unidade": "kgCOD/m³"
                    if k.startswith(("S_su", "S_aa", "S_I", "X_"))
                    else "kmol/m³",
                }
                for k, v in _influent.items()
            ]
            st.dataframe(_result_rows, use_container_width=True)
            _bc1, _bc2 = st.columns(2)
            _bc1.metric("Erro balanço COD", f"{_balance['cod_error_pct']:.3f}%")
            _bc2.metric("Erro balanço N", f"{_balance['n_error_pct']:.1f}%")
            if _balance["cod_error_pct"] > 1.0:
                st.warning("Erro de COD > 1% — verificar se as frações somam 1.0")

        if "asm1_adm1_influent" in st.session_state:
            if st.button("✅ Usar como influente desta simulação", key="a1_use_influent"):
                _inf = st.session_state["asm1_adm1_influent"]
                _pcod = (
                    _inf.get("X_ch", 0.0) + _inf.get("X_pr", 0.0) + _inf.get("X_li", 0.0)
                    + _inf.get("X_xc", 0.0) + _inf.get("X_I", 0.0)
                )
                _scod = _inf.get("S_su", 0.0) + _inf.get("S_aa", 0.0) + _inf.get("S_I", 0.0)
                _sin_kgN = _inf.get("S_IN", 0.0) * 14.0
                _alk = max(_inf.get("S_IC", 0.1), 0.1)
                st.session_state["manual_feed_name"] = "Influente ASM1→ADM1 (E14)"
                st.session_state["manual_particulate_cod"] = float(_pcod)
                st.session_state["manual_soluble_cod"] = float(_scod)
                st.session_state["manual_acetate"] = 0.0
                st.session_state["manual_propionate"] = 0.0
                st.session_state["manual_hydrogen"] = 0.0
                st.session_state["manual_inorganic_nitrogen"] = float(_sin_kgN)
                st.session_state["manual_alkalinity"] = float(st.session_state.get("manual_alkalinity", 4.0))
                st.session_state["manual_sic_kmol_m3"] = float(_alk)
                st.session_state["manual_feed_ph"] = 7.0
                st.session_state["sim_substrate_mode"] = "manual"
                st.session_state["sim_skip_base_reset"] = True
                st.success("Influente ADM1 aplicado. Modo trocado para 'Manual temporário'.")
                st.rerun()


def _render_composition_converter() -> None:
    """Renderiza o painel de conversão de composição bioquímica → ADM1."""
    with st.expander("🧪 Converter composição do cliente → ADM1", expanded=False):
        st.caption(
            "Informe a composição em **base úmida** (% do peso fresco). "
            "Outros carboidratos são calculados automaticamente."
        )

        # Row 1: name + dry matter + organic matter
        col1, col2, col3 = st.columns(3)
        sample_name = col1.text_input("Nome da amostra", value="Amostra", key="conv_sample_name")
        dry_matter = col2.number_input("Matéria seca (%BU)", 0.1, 100.0, 10.0, step=0.1, key="conv_dry_matter_pct")
        organic_matter = col3.number_input("Matéria orgânica (%BU)", 0.0, 100.0, 7.0, step=0.1, key="conv_organic_matter_pct")

        # Row 2: protein + lipids + cellulose + lignin
        col4, col5, col6, col7 = st.columns(4)
        protein = col4.number_input("Proteína (%BU)", 0.0, 100.0, 1.0, step=0.1, key="conv_protein_pct")
        lipids = col5.number_input("Lipídeos (%BU)", 0.0, 100.0, 1.0, step=0.1, key="conv_lipids_pct")
        cellulose = col6.number_input("Celulose (%BU)", 0.0, 100.0, 2.0, step=0.1, key="conv_cellulose_pct")
        lignin = col7.number_input("Lignina (%BU)", 0.0, 100.0, 0.5, step=0.1, key="conv_lignin_pct")

        # Show calculated "outros carboidratos" (read-only)
        other_carb = organic_matter - protein - lipids - cellulose - lignin
        if other_carb < 0:
            st.warning(f"⚠️ Outros carboidratos negativos ({other_carb:.2f}%). Revise a composição.")
        else:
            st.caption(f"📊 Outros carboidratos (calculado): **{other_carb:.2f}** %BU")

        # Row 3: optional fields
        st.markdown("**Parâmetros opcionais** (quando disponíveis)")
        col8, col9, col10 = st.columns(3)
        ph_input = col8.number_input(
            "pH", 0.0, 14.0, 0.0, step=0.1, key="conv_ph_input",
            help="Deixe 0 para usar default (7.0 assumido)",
        )
        alk_input = col9.number_input(
            "Alcalinidade (mEq/L)", 0.0, 2000.0, 0.0, step=1.0, key="conv_alk_meq_l",
            help="Deixe 0 para usar default",
        )
        tan_input = col10.number_input(
            "TAN/NH₄⁺ (mg N/L)", 0.0, 5000.0, 0.0, step=1.0, key="conv_tan_mg_l",
            help="Deixe 0 quando não medido",
        )

        # Convert to None when 0 (0 means "not provided")
        ph_val = ph_input if ph_input > 0.0 else None
        alk_val = alk_input if alk_input > 0.0 else None
        tan_val = tan_input if tan_input > 0.0 else None

        # Calculate button
        if st.button("▶ Converter composição", key="conv_calculate"):
            import dataclasses

            from simulator.substrate_conversion.contracts import CompositionInput
            from simulator.substrate_conversion.service import convert_composition_to_adm1

            inp = CompositionInput(
                sample_name=sample_name,
                dry_matter_pct=dry_matter,
                organic_matter_pct=organic_matter,
                protein_pct=protein,
                lipids_pct=lipids,
                cellulose_pct=cellulose,
                lignin_pct=lignin,
                ph=ph_val,
                alkalinity_meq_l=alk_val,
                tan_mg_l=tan_val,
            )
            try:
                result = convert_composition_to_adm1(inp)
                st.session_state["conv_composition_input"] = dataclasses.asdict(inp)
                st.session_state["conv_composition_result"] = dataclasses.asdict(result)
                st.session_state["conv_full_influent_state_overrides"] = dataclasses.asdict(
                    result.full_influent_state_overrides
                )
                st.session_state["conv_conversion_assumptions"] = [
                    dataclasses.asdict(a) for a in result.assumptions_used
                ]
                st.session_state["conv_conversion_warnings"] = list(result.warnings)
                st.session_state["conv_conversion_applied_to_manual"] = False
                st.rerun()
            except ValueError as e:
                st.error(f"Erro na conversão: {e}")

        # Show results if available
        if st.session_state.get("conv_composition_result"):
            result_dict = st.session_state["conv_composition_result"]
            rf = result_dict.get("reduced_feed_values", {})
            fi = result_dict.get("full_influent_state_overrides", {})

            st.markdown("**Resultado da conversão**")

            # Summary metrics (units in label to avoid misuse of delta parameter)
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("COD particulado (kgCOD/m³)", f"{rf.get('particulate_cod', 0):.2f}")
            mc2.metric("COD solúvel (kgCOD/m³)", f"{rf.get('soluble_cod', 0):.2f}")
            mc3.metric("N inorgânico (kgN/m³)", f"{rf.get('inorganic_nitrogen', 0):.3f}")
            mc4.metric("pH efetivo", f"{rf.get('ph', 7.0):.1f}")

            # Full influent state table (filter out None and zero values)
            state_rows = []
            for k, v in fi.items():
                if v is None or v == 0.0:
                    continue
                if k in ("S_IN",):
                    unit = "kgN/m³"
                elif k in ("S_IC",):
                    unit = "kmol/m³"
                elif k == "ph":
                    unit = "—"
                else:
                    unit = "kgCOD/m³"
                state_rows.append({"Estado ADM1": k, "Valor": f"{v:.4f}", "Unidade": unit})
            if state_rows:
                st.dataframe(state_rows, use_container_width=True)

            # Warnings
            for w in st.session_state.get("conv_conversion_warnings", []):
                st.warning(w)

            # Assumptions
            assumptions_list = st.session_state.get("conv_conversion_assumptions", [])
            if assumptions_list:
                with st.expander("📋 Hipóteses adotadas", expanded=False):
                    for a in assumptions_list:
                        st.caption(
                            f"**{a.get('field', '')}** = {a.get('assumed_value', '')} "
                            f"— {a.get('reason', '')}"
                        )

            # Action buttons
            ba1, ba2 = st.columns(2)

            if ba1.button("✅ Aplicar ao modo manual", key="conv_apply_manual"):
                st.session_state["manual_feed_name"] = (
                    st.session_state.get("conv_sample_name", "Amostra") + " (conversor composição)"
                )
                st.session_state["manual_particulate_cod"] = float(rf.get("particulate_cod", 8.0))
                st.session_state["manual_soluble_cod"] = float(rf.get("soluble_cod", 4.0))
                st.session_state["manual_acetate"] = float(rf.get("acetate", 0.0))
                st.session_state["manual_propionate"] = float(rf.get("propionate", 0.0))
                st.session_state["manual_hydrogen"] = float(rf.get("hydrogen", 0.0))
                st.session_state["manual_inorganic_nitrogen"] = float(rf.get("inorganic_nitrogen", 1.0))
                st.session_state["manual_alkalinity"] = float(rf.get("alkalinity", 4.0))
                st.session_state["manual_sic_kmol_m3"] = float(rf.get("sic_kmol_m3") or 0.0)
                st.session_state["manual_feed_ph"] = float(rf.get("ph", 7.0))
                st.session_state["sim_substrate_mode"] = "manual"
                st.session_state["sim_skip_base_reset"] = True
                st.session_state["conv_conversion_applied_to_manual"] = True
                st.success("Composição convertida aplicada ao modo manual.")
                st.rerun()

            if ba2.button("💾 Salvar como substrato personalizado", key="conv_save_custom"):
                from webapp.services.preferences_service import save_custom_substrate_with_provenance

                save_name = st.session_state.get("conv_sample_name", "Amostra")
                values = {
                    "particulate_cod": float(rf.get("particulate_cod", 0.0)),
                    "soluble_cod": float(rf.get("soluble_cod", 0.0)),
                    "acetate": float(rf.get("acetate", 0.0)),
                    "propionate": float(rf.get("propionate", 0.0)),
                    "hydrogen": float(rf.get("hydrogen", 0.0)),
                    "inorganic_nitrogen": float(rf.get("inorganic_nitrogen", 0.0)),
                    "alkalinity": float(rf.get("alkalinity", 4.0)),
                    "sic_kmol_m3": float(rf.get("sic_kmol_m3") or 0.0),
                    "ph": float(rf.get("ph", 7.0)),
                }
                try:
                    save_custom_substrate_with_provenance(
                        save_name,
                        values,
                        composition_input=st.session_state.get("conv_composition_input"),
                        assumptions=st.session_state.get("conv_conversion_assumptions"),
                        warnings=st.session_state.get("conv_conversion_warnings"),
                    )
                    st.success(f"Substrato '{save_name}' salvo com proveniência.")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
