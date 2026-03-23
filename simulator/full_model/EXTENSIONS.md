# ADM1 Full Model — Extensions Guide

This document describes the extension system for the ADM1 full backend, listing all available extensions, their parameters, how to use them from each interface, and how to create custom extensions.

## Available Extensions

| ID | Name | States | Processes | Literature | Domain |
|----|------|--------|-----------|------------|--------|
| `srb` | Sulfate-Reducing Bacteria (E4) | 7 | 8 | Fedorovich et al. (2003); Barrera et al. (2015) | General (high-sulfate wastewaters) |
| `lcfa_adsorption` | LCFA Adsorption (E5) | 1 | 3 | Palatsi et al. (2010); Zonta et al. (2013) | General (lipid-rich substrates) |
| `lactate` | Lactate Pathway (E6) | 2 | 2 | Satpathy et al. (2016) | General |
| `ethanol` | Ethanol Pathway (E10) | 2 | 2 | García-Gen et al. (2013) | General |
| `phenolics` | Phenolics (E11) | 3 | 2 | Fezzani & Ben Cheikh (2008, 2009) | **Olive mill wastewater only** |
| `pilot_tracer` | Pilot Tracer (E0) | 1 | 1 | — | Testing/validation |

> **Note:** Extensions are only active when the backend is `full`. The `reduced` and `pyadm1` backends ignore extension settings.

---

## Extension Details

### E4 — Sulfate-Reducing Bacteria (`srb`)

Models competition between sulfate-reducing bacteria (SRB) and methanogens for acetate, hydrogen, propionate, and butyrate. Includes H₂S production, gas-phase stripping, and cross-process inhibition.

**New states:** `S_SO4`, `S_H2S`, `S_gas_H2S`, `X_SRB_ac`, `X_SRB_h2`, `X_SRB_pro`, `X_SRB_bu`

**Key parameters:**

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `k_m_SRB_ac` | 7.1 | d⁻¹ | Max uptake rate, SRB acetate |
| `k_m_SRB_h2` | 26.7 | d⁻¹ | Max uptake rate, SRB hydrogen |
| `K_I_H2S` | 6.72e-3 | kmolS/m³ | H₂S inhibition threshold |
| `K_S_SO4_ac` | 3.1e-4 | kmol/m³ | SO₄ half-saturation (acetate SRB) |

**Inhibition:** First-order linear H₂S inhibition on methanogenesis and VFA degradation (Fedorovich 2003 Eq. 11):
`I_H2S = max(0, 1 − S_H2S / K_I_H2S)`

**Typical initial state overrides:**
```python
full_initial_state_overrides={"S_SO4": 0.005}  # kmol/m³
```

### E5 — LCFA Adsorption (`lcfa_adsorption`)

Models adsorption/desorption of long-chain fatty acids onto biomass surfaces, adding a kinetic intermediate (`X_LCFA_ads`) that modulates LCFA bioavailability.

**New state:** `X_LCFA_ads`

**Key parameters:**

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `k_ads_LCFA` | 10.0 | m³/(kgCOD·d) | Adsorption rate |
| `k_des_LCFA` | 0.2 | d⁻¹ | Desorption rate |
| `k_m_LCFA_ads` | 21.69 | d⁻¹ | Adsorbed LCFA degradation rate |
| `K_I_LCFA_ads` | 3.35 | kgCOD/m³ | Contact inhibition threshold |

**Inhibition:** Non-competitive contact inhibition on core LCFA uptake (rho_7):
`I_LCFA = K_I / (K_I + X_LCFA_ads)`

### E6 — Lactate Pathway (`lactate`)

Adds lactate as a fermentation intermediate, consumed by dedicated acetogens producing acetate, propionate, and hydrogen.

**New states:** `S_lac`, `X_lac`

**Key parameters:**

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `k_m_lac` | 13.0 | d⁻¹ | Max lactate uptake rate |
| `K_S_lac` | 0.08 | kgCOD/m³ | Half-saturation |
| `Y_lac` | 0.06 | kgCOD/kgCOD | Yield |
| `f_lac_su` | 0.10 | — | Sugar overflow fraction to lactate |

**Sugar overflow:** When active, a fraction `f_lac_su` of sugar uptake products (rho_5) is redirected to S_lac instead of VFAs. This is the Satpathy (2016) overflow mechanism.

### E10 — Ethanol Pathway (`ethanol`)

Adds ethanol as a fermentation intermediate, consumed by dedicated acetogens producing acetate and hydrogen.

**New states:** `S_et`, `X_et`

**Key parameters:**

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `k_m_et` | 3.0 | d⁻¹ | Max ethanol uptake rate |
| `K_S_et` | 0.50 | kgCOD/m³ | Half-saturation |
| `Y_et` | 0.05 | kgCOD/kgCOD | Yield |
| `f_et_su` | 0.05 | — | Sugar overflow fraction to ethanol |

**Sugar overflow:** When active, fraction `f_et_su` of rho_5 products redirected to S_et (García-Gen 2013).

### E11 — Phenolics (`phenolics`)

Two-step degradation of phenolic compounds: phenol → benzoate → acetate. Includes Haldane-type (squared) inhibition on methanogenesis.

**New states:** `S_phen`, `S_ben`, `X_phen`

**Key parameters:**

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `k_m_phen` | 0.8 | d⁻¹ | Max phenol uptake rate |
| `K_S_phen` | 30.5 | kgCOD/m³ | Half-saturation (very high — olive mill) |
| `K_I_phen` | 50.0 | kgCOD/m³ | Phenol inhibition threshold |

**⚠️ Domain restriction:** Parameters calibrated **exclusively for olive mill wastewater** (S_phen ≈ 5–50 kgCOD/m³). Any other substrate requires complete recalibration.

**Inhibition:** Haldane squared on acetoclastic and hydrogenotrophic methanogenesis:
`I_phen = 1 / (1 + (S_phen / K_I_phen)²)`

---

## Usage

### Python API

```python
from simulator.service import ADM1SimulationService
from simulator.core.models import SimulationConfig

service = ADM1SimulationService()
result = service.simulate(
    "cstr",
    simulation=SimulationConfig(
        duration_days=60,
        backend="full",
        full_extensions=["srb", "lactate"],
        full_extension_parameter_overrides={"K_I_H2S": 0.01},
        full_initial_state_overrides={"S_SO4": 0.005},
    ),
)
```

### Webapp

In the **Simular Reator** page, select the `full` backend. A multiselect widget appears listing all available extensions. Extension-specific KPIs and profile charts are shown automatically.

### CLI (Design Pipeline)

```bash
python -m simulator.design_pipeline \
    --substrate "Lodo de Esgoto" \
    --backend full \
    --extensions srb lactate \
    --extension-params K_I_H2S=0.01
```

### MCP Tools

All simulation tools accept optional extension parameters:

```json
{
  "reactor_type": "cstr",
  "backend": "full",
  "full_extensions": ["srb", "lactate"],
  "full_extension_parameter_overrides": {"K_I_H2S": 0.01},
  "full_initial_state_overrides": {"S_SO4": 0.005}
}
```

Use `list_extensions` to discover available extensions:
```
→ list_extensions()
```

---

## Creating Custom Extensions

Extensions implement the `FullModelExtension` protocol:

```python
from simulator.full_model.extensions import FullModelExtension, FullModelExtensionContribution

class MyExtension:
    name = "my_extension"
    description = "Description of what this extension does."

    def contribute(self) -> FullModelExtensionContribution:
        return FullModelExtensionContribution(
            states=(...),           # Tuple of StateDefinition
            processes=(...),        # Tuple of ProcessDefinition
            parameters=(...),       # Tuple of ParameterDefinition
            biochemical_stoichiometry_rows={...},  # New process rows
            stoichiometry_patches={...},           # Patches to existing rows
            rate_function=self._rates,
            inhibition_hook=self._inhibition,      # Optional
            diagnostics_hook=self._diagnostics,    # Optional
        )
```

Register in `simulator/full_model/extension_registry.py`:

```python
EXTENSION_REGISTRY["my_extension"] = MyExtension()
```

See `pilot_tracer_extension.py` for a minimal working example.

---

## Known Limitations (v1)

1. **E5 k_ads/k_des:** Ad-hoc estimates without experimental validation source (documented in code).
2. **E11 domain:** Phenolics parameters calibrated exclusively for olive mill wastewater.
3. **E4 k_La_H2S:** Uses same k_La as CO₂/CH₄ (200 d⁻¹); H₂S diffusivity differences not accounted for.
4. **Extensions E1–E3:** Enhanced ammonia inhibition, co-digestion blending, and process variants are planned but not yet implemented.
