# Relatório de validação numérica — tarefa V

Auditoria em 2026-11-01, sobre `a9311ad` (PR #20), com Python 3.12.15,
NumPy 2.5.4 e SciPy 1.18.1. O requisito Python 3.11+ está atendido.
Nenhuma constante publicada, cinética ou estequiometria foi recalibrada nesta tarefa.

## Conclusões

- **BSM2 publicado aprovado:** 46 grandezas da Tabela 6 e uma vazão de metano
  derivada, para full e PyADM1 em 200 dias. Limite relativo: **0,1%**;
  piso absoluto: **1e-14**, inclusive para H₂ e H⁺. Não há exceção que esconda
  desvios de hidrogênio. Maior erro: **0,004940943%** em `S_ac_ion` (PyADM1).
- Full em 400 dias também aprova as 47 comparações. Maior erro relativo:
  **0,00000103955%**, em H⁺, cuja referência tem apenas 8 algarismos significativos.
- Os seis cenários full/PyADM1 passam após o aperto das tolerâncias. O maior
  erro relativo dos estados internos é **0,00000229873%** (`S_ac`, HRT 15 d).
- Reduced e PyADM1 **não são intercambiáveis**: diferença média do metano final
  **20,24793%**. O reduced continua sendo uma aproximação exploratória.
- OpenModelica não está disponível. Não houve validação externa com Modelica.
- Há uma falha numérica adicional em PyADM1/BDF com 400 dias/201 pontos,
  detalhada abaixo. A execução canônica de 200 dias/201 pontos aprova.

## Comandos e artefatos

```bash
.venv/bin/python -m simulator.benchmark
.venv/bin/python -m simulator.validation
.venv/bin/python -m simulator.design_pipeline --substrate "Lodo de Esgoto" --goal balanced --backend auto
.venv/bin/python -m simulator.literature_validation
.venv/bin/python -m simulator.full_parity
.venv/bin/python -m pytest simulator/tests/test_literature_validation.py simulator/tests/test_full_model_phase3.py simulator/tests/test_math_review_literature.py simulator/tests/test_microalgae_literature_validation.py simulator/tests/test_syngas_literature_validation.py simulator/tests/test_trace_elements_literature_validation.py -q
.venv/bin/python -m pytest simulator/tests/test_bsm2_published_steady_state.py simulator/tests/test_validation_reporting.py -q
.venv/bin/python -m pytest simulator/tests -q
```

Os três fluxos solicitados terminaram sem erro. Benchmark e validação gravam
artefatos locais ignorados em `simulator/benchmarks/` e `simulator/validation_runs/`.
A validação da literatura grava em `simulator/literature_validation_runs/`;
a paridade grava em `simulator/full_parity_runs/`. Esses resultados gerados não
fazem parte das alterações a integrar. Os CLIs agora imprimem caminhos relativos.

Reprodução da comparação publicada em memória, sem arquivos privados:

```python
from simulator.bsm2_published import run_published_steady_state_case

for backend in ("full", "pyadm1"):
    report = run_published_steady_state_case(backend, duration_days=200.0)
    assert report["validated"], report["comparison"]
```

O teste novo leva cerca de 13 s junto aos testes de relatório, portanto **não**
recebeu `slow`. `pytest.ini` define `-m "not slow"`; o CI chama pytest sem
sobrescrever essa seleção. A comparação publicada nova participa do CI padrão.

## Origem das referências e critérios

`simulator/benchmark.py` compara reduced com PyADM1 em quatro alimentações
sintéticas, por 30 dias/121 pontos. `baseline_bsm2_like` é apenas semelhante ao
caso do projeto: **não** é a entrada publicada BSM2. A referência operacional
é a execução PyADM1 da mesma alimentação, não uma fixture histórica. Compara
nove métricas finais/acumuladas e cinco séries. Erro relativo usa PyADM1 no
denominador. NRMSE usa `max(max(abs(referência)), ptp(referência), 1e-9)`.
A recomendação de intercambialidade exige simultaneamente médias de erro do
metano final ≤15%, pH ≤3% e NRMSE do metano ≤20%; esses limites são critérios
para modelos distintos, não tolerâncias de fidelidade BSM2, e foram preservados.

`simulator/validation.py` repete esse benchmark, exporta cenários e detecta
`omc`/OMPython/arquivos `.mo`. Não compara números com uma terceira implementação.
Neste ambiente o status é `toolchain_not_available`, `openmodelica_executed=false`
e validação externa pendente. Mesmo com a ferramenta disponível, o código atual
apenas detecta a ferramenta; o status `completed` seria inferido de prontidão.
A execução efetiva de um modelo Modelica continua pendente.

`simulator/design_pipeline.py` faz triagem de três reatores com o preset
`Lodo de Esgoto`, 45 dias/181 pontos. Não há referência publicada nem teste de
aderência numérica nessa classificação. O score usa normalização entre candidatos
e pesos `balanced`: metano 0,35; estabilidade 0,20; efluente 0,20; VFA 0,10; pH 0,15.
A normalização min–max favorece metano maior e estabilidade/VFA/DQO menores.
O componente de pH usa `max(0, 1 - abs(pH - 7,1)/0,6)`, um alvo de projeto,
não uma referência experimental. Candidatos empatados em uma métrica recebem 1.
A classificação mistura backends e deve ser lida como triagem.

`simulator/literature_validation.py` já usava os valores completos das Tabelas
5/6, mas comparava apenas nove saídas PyADM1 em 200 dias. `full_parity.py` usa
os mesmos vetores completos, por 200 dias/121 pontos, BDF, rtol=1e-8, atol=1e-10,
e aplica seis perturbações de entrada/operação. A nova comparação publicada em
`simulator/bsm2_published.py` usa BDF, rtol=1e-10, atol=1e-12 e pontos diários.
Os valores científicos permanecem em uma fixture de validação, separados dos
defaults operacionais.

## Benchmark reduced × PyADM1

Valores atuais; erros relativos sempre contra PyADM1. Nenhum valor antigo foi
usado para forçar aprovação.

| Cenário | Métrica | Reduced | PyADM1 | Erro (%) |
| --- | --- | ---: | ---: | ---: |
| baseline_bsm2_like | methane_final_m3_day | 726.098842 | 624.230782 | 16.318974 |
| baseline_bsm2_like | biogas_final_m3_day | 1204.68417 | 992.512241 | 21.377261 |
| baseline_bsm2_like | ph_final | 7.23160327 | 7.42761172 | 2.638916 |
| baseline_bsm2_like | vfa_final | 0.441035282 | 0.140789147 | 213.259433 |
| baseline_bsm2_like | effluent_cod_final | 6.58370844 | 10.4037972 | 36.718216 |
| higher_loading_short_hrt | methane_final_m3_day | 631.391852 | 1009.19237 | 37.435927 |
| higher_loading_short_hrt | biogas_final_m3_day | 1066.82333 | 1613.91669 | 33.898488 |
| higher_loading_short_hrt | ph_final | 7.16341866 | 7.45058134 | 3.854232 |
| higher_loading_short_hrt | vfa_final | 1.27091817 | 0.434664638 | 192.390514 |
| higher_loading_short_hrt | effluent_cod_final | 14.2771368 | 11.626178 | 22.801636 |
| cooler_buffered_digester | methane_final_m3_day | 581.062974 | 477.919546 | 21.581756 |
| cooler_buffered_digester | biogas_final_m3_day | 963.460066 | 747.158053 | 28.949968 |
| cooler_buffered_digester | ph_final | 7.28289293 | 7.43244641 | 2.012170 |
| cooler_buffered_digester | vfa_final | 0.393092918 | 0.0842703611 | 366.466398 |
| cooler_buffered_digester | effluent_cod_final | 6.25341001 | 9.8779674 | 36.693352 |
| vfa_rich_feed | methane_final_m3_day | 700.860651 | 663.347908 | 5.655063 |
| vfa_rich_feed | biogas_final_m3_day | 1153.05365 | 1045.30612 | 10.307749 |
| vfa_rich_feed | ph_final | 7.20331239 | 7.43464386 | 3.111534 |
| vfa_rich_feed | vfa_final | 0.468680377 | 0.168332327 | 178.425652 |
| vfa_rich_feed | effluent_cod_final | 6.38553973 | 9.10066833 | 29.834387 |

| Métrica agregada | Erro médio (%) | Erro máximo (%) |
| --- | ---: | ---: |
| methane_final_m3_day | 20.247930 | 37.435927 |
| methane_cumulative_m3 | 29.379407 | 36.470599 |
| biogas_final_m3_day | 23.633366 | 33.898488 |
| ch4_fraction_final | 4.862714 | 5.714008 |
| ph_final | 2.904213 | 3.854232 |
| vfa_final | 237.635499 | 366.466398 |
| effluent_cod_final | 31.511898 | 36.718216 |
| volatile_solids_proxy | 52.965360 | 55.567228 |
| stability_index | 1449.990236 | 1913.952290 |

| Série | NRMSE médio (%) | NRMSE máximo (%) |
| --- | ---: | ---: |
| methane_m3_day | 9.920646 | 10.321331 |
| biogas_m3_day | 10.296480 | 10.764061 |
| ph | 2.633796 | 3.314079 |
| vfa_total | 21.424395 | 23.447586 |
| effluent_cod | 13.701144 | 14.619024 |

O metano médio final ultrapassa o limite de 15%. O pH médio (2,904213%) e o
NRMSE médio do metano (9,920646%) passam seus critérios agregados. Individualmente,
o pH ultrapassa 3% em `higher_loading_short_hrt` e `vfa_rich_feed`. VFA e DQO
mostram diferenças grandes, mas o benchmark não estabelece gates para eles.
As diferenças decorrem das estruturas distintas dos modelos, especialmente
agregação de substratos/biomassa, nitrogênio e inibição do reduced. Não há motivo
para alterar PyADM1 para reproduzir o reduced.

## Triagem de projeto

| Reator | Backend usado | Score | CH₄ (m³/d) | Biogás (m³/d) | pH | DQO efluente (kg/m³) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| cstr | pyadm1 | 0.878009369 | 619.841613 | 986.105718 | 7.436087467 | 9.673437390 |
| uasb | full | 0.712961048 | 652.509412 | 1036.272299 | 7.448155807 | 18.580724943 |
| plug_flow | reduced | 0.291859517 | 248.431309 | 435.105349 | 7.138727835 | 11.831607429 |

Recomendação atual: CSTR. `plug_flow/auto` fez fallback explícito para reduced,
por custo computacional do full. Isso não representa aprovação de dimensionamento
com o reduced. A diferença entre 624,230782 m³/d no benchmark e 619,841613 m³/d
na triagem CSTR vem também das durações de 30 e 45 dias, respectivamente.

## BSM2 publicado: entrada, formulações e unidades

Fonte: Rosén & Jeppsson (2008), *Aspects on ADM1 Implementation within the BSM2
Framework*, [PDF original](https://assets.pubpub.org/awqjabxp/51603224611145.pdf),
Tabelas 5 e 6, pp. 21–22, §§3.5.4, 4.2 e 8.1. O texto convertido local arredonda
valores; a transcrição em código foi conferida contra os números completos do PDF.
As nove referências pré-existentes são preservadas bit a bit.

Volume líquido 3400 m³, volume gasoso 300 m³, vazão 170 m³/d, HRT 20 d e 35 °C.
A entrada explícita da Tabela 5 evita o mapeamento agregado afetado pelos PRs #6/#7.
Concentrações orgânicas em kgDQO/m³; `S_IC` em kmolC/m³; `S_IN` em kmolN/m³;
cátions e ânions em kmol de carga/m³.

```json
{
  "S_su": 0.01,
  "S_aa": 0.001,
  "S_fa": 0.001,
  "S_va": 0.001,
  "S_bu": 0.001,
  "S_pro": 0.001,
  "S_ac": 0.001,
  "S_h2": 1e-08,
  "S_ch4": 1e-05,
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
  "S_anion": 0.02
}
```

O estado inicial vem de `vendor/PyADM1/src/digester_initial.csv`, não da saída
publicada. Não se inicializa o simulador na solução esperada. O cátion inicial
é próximo de zero e o ânion inicial é 0,0052101, distintos da entrada de 0,04/0,02;
suas diferenças ainda decaem como `exp(-t/HRT)` aos 200 dias.

- **Full:** 29 estados diferenciais, incluindo H₂ dissolvido, com equilíbrio
  ácido-base algébrico a cada avaliação; equivalente à formulação **DAE1**.
- **PyADM1 integrado:** pH e H₂ dissolvido algébricos a cada avaliação;
  equivalente à formulação **DAE2**. Usa `solve_ivp` com variáveis algébricas
  reconstruídas, não um solver DAE de matriz de massa.
- A versão puramente ODE com relaxação cinética das seis reações ácido-base
  do §3.3 não existe como opção executável no projeto. Não se deve chamar a
  comparação DAE1/DAE2 abaixo de comparação com essa ODE completa.

A Tabela 6 usa `Qgas` à pressão atmosférica (1,013 bar), e não à pressão do
headspace. Os perfis atuais aplicam `q_headspace * Pgas / Patm`. O nome legado
`Nm3_day` foi mantido para compatibilidade com a referência, mas **não** indica
normalização térmica para 0 °C nem remoção de vapor d'água: é gás úmido a 35 °C.
A Tabela 6 não traz `q_ch4` diretamente. A última linha abaixo é **derivada**:
`Qch4 = Qgas * p_gas_ch4 / Pgas = 1799,328285311 m³/d`, na mesma base.
Não se deve comparar a vazão de metano no headspace com essa vazão atmosférica.

## Comparação completa com a Tabela 6

Erro percentual absoluto, sem recalibração das referências. Todos os valores
abaixo passam o limite relativo de 0,1%. `Q` e `T_op` são condições impostas;
as pressões são calculadas dos estados gasosos e a vazão vem dos perfis de saída.
As execuções da tabela usam 201 pontos em cada horizonte. O teste usa 201 pontos
em 200 dias e 401 em 400 dias; no full, `t_eval` só amostra a trajetória integrada.

| Grandeza | Unidade | Publicado / derivado | Full 200 d | Erro (%) | PyADM1 200 d | Erro (%) | Full 400 d | Erro (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S_su | kgDQO/m³ | 0.011954829716958 | 0.0119548338166 | 3.429243e-05 | 0.0119548338166 | 3.429306e-05 | 0.011954829717 | 9.243284e-11 |
| S_aa | kgDQO/m³ | 0.005314740171633 | 0.0053147413363 | 2.191396e-05 | 0.00531474133632 | 2.191432e-05 | 0.00531474017164 | 7.345599e-11 |
| S_fa | kgDQO/m³ | 0.098621400930799 | 0.0986213841233 | 1.704248e-05 | 0.0986213841232 | 1.704252e-05 | 0.0986214009309 | 7.479152e-11 |
| S_va | kgDQO/m³ | 0.011625006463861 | 0.0116250093392 | 2.473388e-05 | 0.0116250093392 | 2.47343e-05 | 0.0116250064639 | 7.725298e-11 |
| S_bu | kgDQO/m³ | 0.013250729666269 | 0.0132507329498 | 2.477999e-05 | 0.0132507329499 | 2.478041e-05 | 0.0132507296663 | 7.964888e-11 |
| S_pro | kgDQO/m³ | 0.015783666284542 | 0.0157836715561 | 3.339856e-05 | 0.0157836715561 | 3.339913e-05 | 0.0157836662846 | 9.555249e-11 |
| S_ac | kgDQO/m³ | 0.197629716937552 | 0.197619959521 | 0.004937221 | 0.197619959249 | 0.004937359 | 0.197629716474 | 2.345279e-07 |
| S_h2 | kgDQO/m³ | 2.35945059e-07 | 2.35945100827e-07 | 1.77274e-05 | 2.35945100828e-07 | 1.772776e-05 | 2.35945058848e-07 | 6.439925e-08 |
| S_ch4 | kgDQO/m³ | 0.055088776445959 | 0.0550887764307 | 2.761077e-08 | 0.0550887764307 | 2.764471e-08 | 0.055088776446 | 3.536912e-11 |
| S_IC | kmolC/m³ | 0.152677870626333 | 0.152675267947 | 0.001704687 | 0.152675267874 | 0.001704734 | 0.152677870503 | 8.067687e-08 |
| S_IN | kmolN/m³ | 0.130229815803682 | 0.130228078652 | 0.001333913 | 0.130228078603 | 0.00133395 | 0.130229815721 | 6.329968e-08 |
| S_I | kgDQO/m³ | 0.328697663721532 | 0.32868520964 | 0.003788917 | 0.328685209292 | 0.003789023 | 0.328697663128 | 1.805616e-07 |
| X_xc | kgDQO/m³ | 0.308697663721532 | 0.308697636867 | 8.699192e-06 | 0.308697636867 | 8.699347e-06 | 0.308697663721 | 1.235389e-11 |
| X_ch | kgDQO/m³ | 0.02794724043504 | 0.027947240166 | 9.626244e-07 | 0.027947240166 | 9.626416e-07 | 0.027947240435 | 9.310705e-13 |
| X_pr | kgDQO/m³ | 0.102574106106682 | 0.102574105838 | 2.622759e-07 | 0.102574105838 | 2.622806e-07 | 0.102574106107 | 4.735333e-13 |
| X_li | kgDQO/m³ | 0.029483049707287 | 0.0294830493037 | 1.368722e-06 | 0.0294830493037 | 1.368747e-06 | 0.0294830497073 | 3.483209e-12 |
| X_su | kgDQO/m³ | 0.420165982454567 | 0.420165842062 | 3.341364e-05 | 0.420165842059 | 3.341423e-05 | 0.420165982454 | 4.4867e-11 |
| X_aa | kgDQO/m³ | 1.1791717989237 | 1.17917155418 | 2.075573e-05 | 1.17917155417 | 2.075607e-05 | 1.17917179892 | 2.267199e-11 |
| X_fa | kgDQO/m³ | 0.243035344719442 | 0.243035378593 | 1.393773e-05 | 0.243035378593 | 1.393778e-05 | 0.243035344719 | 9.056366e-12 |
| X_c4 | kgDQO/m³ | 0.431921105635979 | 0.431921010003 | 2.21412e-05 | 0.431921010002 | 2.214156e-05 | 0.431921105636 | 2.421345e-11 |
| X_pro | kgDQO/m³ | 0.137305908933954 | 0.137305871708 | 2.711189e-05 | 0.137305871707 | 2.711234e-05 | 0.137305908934 | 3.054397e-11 |
| X_ac | kgDQO/m³ | 0.760562658313215 | 0.760562548778 | 1.440183e-05 | 0.760562548776 | 1.44021e-05 | 0.760562658313 | 3.389514e-11 |
| X_h2 | kgDQO/m³ | 0.317022953361272 | 0.317022899874 | 1.687173e-05 | 0.317022899873 | 1.687206e-05 | 0.317022953361 | 2.528464e-11 |
| X_I | kgDQO/m³ | 25.6173953274431 | 25.6170069747 | 0.001515973 | 25.6170069638 | 0.001516015 | 25.617395309 | 7.185374e-08 |
| S_cation | kmol/m³ | 0.04 | 0.0399981840345 | 0.004539914 | 0.0399981839838 | 0.00454004 | 0.039999999914 | 2.151017e-07 |
| S_anion | kmol/m³ | 0.02 | 0.0199993285513 | 0.003357244 | 0.0199993285326 | 0.003357337 | 0.0199999999682 | 1.590667e-07 |
| Q | m³/d | 170 | 170 | 0 | 170 | 0 | 170 | 0 |
| T_op | °C | 35 | 35 | 0 | 35 | 0 | 35 | 0 |
| pH | — | 7.46553776990464 | 7.46552985387 | 0.0001060344 | 7.46552985364 | 0.0001060375 | 7.46553776951 | 5.267607e-09 |
| S_H_ion | kmol/m³ | 3.4234361e-08 | 3.42349853323e-08 | 0.001823701 | 3.42349853505e-08 | 0.001823754 | 3.42343613559e-08 | 1.039546e-06 |
| S_va_ion | kgDQO/m³ | 0.011596247072545 | 0.0115962494178 | 2.022455e-05 | 0.0115962494179 | 2.022483e-05 | 0.0115962470725 | 1.296078e-10 |
| S_bu_ion | kgDQO/m³ | 0.013220826248532 | 0.0132208289808 | 2.066653e-05 | 0.0132208289809 | 2.066683e-05 | 0.0132208262485 | 1.149937e-10 |
| S_pro_ion | kgDQO/m³ | 0.015742783191567 | 0.0157427877062 | 2.867726e-05 | 0.0157427877062 | 2.867769e-05 | 0.0157427831915 | 1.227535e-10 |
| S_ac_ion | kgDQO/m³ | 0.197241155436605 | 0.197231410136 | 0.004940805 | 0.197231409864 | 0.004940943 | 0.197241154974 | 2.346971e-07 |
| S_hco3_ion | kmolC/m³ | 0.142777479392078 | 0.142774876729 | 0.001822881 | 0.142774876656 | 0.001822932 | 0.142777479269 | 8.625951e-08 |
| S_co2 | kmolC/m³ | 0.009900391234255 | 0.00990039121776 | 1.666582e-07 | 0.00990039121797 | 1.644906e-07 | 0.00990039123424 | 1.672453e-10 |
| S_nh3 | kmolN/m³ | 0.004090928458444 | 0.00409080166638 | 0.003099347 | 0.00409080166275 | 0.003099436 | 0.00409092845244 | 1.466847e-07 |
| S_nh4_ion | kmolN/m³ | 0.126138887345238 | 0.126137276985 | 0.001276656 | 0.126137276941 | 0.001276692 | 0.126138887269 | 6.059535e-08 |
| S_gas_h2 | kgDQO/m³ | 1.0241035595e-05 | 1.02410374298e-05 | 1.791654e-05 | 1.02410374298e-05 | 1.791625e-05 | 1.02410355951e-05 | 5.905638e-10 |
| S_gas_ch4 | kgDQO/m³ | 1.62560720998142 | 1.62560721065 | 4.126338e-08 | 1.62560721065 | 4.085645e-08 | 1.62560720998 | 2.229178e-11 |
| S_gas_co2 | kmolC/m³ | 0.014150534678395 | 0.0141505346553 | 1.634459e-07 | 0.0141505346556 | 1.611822e-07 | 0.0141505346784 | 1.540474e-10 |
| p_gas_h2 | bar | 1.639918264e-05 | 1.63991855779e-05 | 1.791499e-05 | 1.63991855779e-05 | 1.79147e-05 | 1.63991826398e-05 | 9.588271e-10 |
| p_gas_ch4 | bar | 0.650779632823186 | 0.650779633092 | 4.126344e-08 | 0.650779633089 | 4.08565e-08 | 0.650779632823 | 2.22461e-11 |
| p_gas_co2 | bar | 0.362552713328102 | 0.362552712736 | 1.634459e-07 | 0.362552712744 | 1.611822e-07 | 0.362552713329 | 1.540766e-10 |
| Pgas_bar | bar | 1.06901649040892 | 1.06901649009 | 3.003748e-08 | 1.06901649009 | 2.951748e-08 | 1.06901649041 | 3.869623e-11 |
| Qgas_Nm3_day | m³/d (atm, 35 °C) | 2955.70345419378 | 2955.70343636 | 6.032703e-07 | 2955.70343667 | 5.92827e-07 | 2955.70345422 | 7.780099e-10 |
| Qch4_Nm3_day (derivado) | m³/d (atm, 35 °C) | 1799.32828530893 | 1799.32827574 | 5.319693e-07 | 1799.32827591 | 5.22453e-07 | 1799.32828532 | 7.170631e-10 |

A queda dos erros entre 200 e 400 dias é compatível com o transiente inicial,
especialmente dos íons conservativos e dos inertes. O maior deslocamento entre
200 e 400 dias fica abaixo de 0,005%, menor que o critério de 0,1%. A regressão
verifica essa estabilidade dos dois resultados de 200 dias contra o full de 400 dias.
Não foi encontrado desvio da tabela maior que 0,1% nos casos aprovados.

## Paridade full × PyADM1 e tolerâncias herdadas

Os limites frouxos já existiam em `092cea1` (estados: 15%, multiplicador 1,5,
piso 1e-6), antes dos PRs #6/#7. Não foi encontrado afrouxamento posterior a
esses PRs nos arquivos auditados. O teste de balanço de microalgas foi adicionado
em `fac246f` já com 5%. A revisão aperta esses limites com base nas execuções atuais.

| Cenário | Maior erro de estado (%) | Maior NRMSE (%) | Erro metano acumulado (%) | Gates novos |
| --- | ---: | ---: | ---: | --- |
| baseline_bsm2_reference | 8.09233854e-07 | 1.55057266e-05 | 0.391773541 | passam |
| high_nitrogen_sin_x2 | 5.09317667e-07 | 1.9896557e-05 | 0.392605344 | passam |
| high_organic_loading_cod_x1_2 | 7.61275148e-07 | 2.25354784e-05 | 0.327221565 | passam |
| short_hrt_15d | 2.29873289e-06 | 1.84588164e-05 | 0.298346813 | passam |
| temperature_25c | 1.22383352e-06 | 6.55436184e-06 | 3.4936195e-08 | passam |
| lipid_rich_influent | 1.33977641e-06 | 5.77762209e-06 | 0.381705378 | passam |

O erro de até 0,392605% do metano acumulado não é erro da cinética estacionária:
o vendor inicia `gasflow` com zero, enquanto o full calcula o gás do estado
inicial. As séries de gases na paridade já excluem esse primeiro ponto. A integral
por trapézios inclui o ponto e difere por aproximadamente `Q_CH4_full(0) * Δt/2`.
O efeito diminui ao refinar a malha: no caso-base, 0,391773% com 121 pontos,
contra aproximadamente 0,2347% com 201 pontos. Por isso o limite específico da
integral é 0,5%, ainda abaixo de 1%, e não os 0,01% das métricas finais.
Não se modificou a política de integração do produto nesta auditoria.

## Mudanças de critérios e referências

Nenhum alvo numérico antigo de publicação ou fixture de saída foi substituído.
Foram adicionadas 37 grandezas publicadas às nove existentes e uma derivação,
sem alterar as nove referências anteriores. Os números medidos neste relatório
substituem apenas afirmações sobre o estado atual, não valores científicos.

| Local / teste | Antigo → novo | Justificativa |
| --- | --- | --- |
| `literature_validation.PYADM1_REL_TOL_PCT` | 0,2% → 0,1% | Critério pedido; erro atual máximo das nove saídas: 0,00493736%. |
| `literature_validation.PYADM1_ABS_TOL` | 1e-5 → 1e-14 | Impede que o piso esconda futuros erros em estados pequenos. |
| `LiteratureValidationTest.test_literature_validation_matches_bsm2_for_pyadm1` | erro máximo <0,2% → <0,1% | Alinha o teste ao limite publicado adotado. |
| `full_parity.INTERNAL_STATE_REL_TOL_PCT` | 15% → 0,01% | Erro medido <0,00000230% nos seis cenários. |
| `full_parity.INTERNAL_STATE_ABS_FLOOR` | 1e-6 → 1e-12 | O piso antigo excedia o próprio H₂ dissolvido. |
| `full_parity.NON_BASELINE_TOLERANCE_MULTIPLIER` | 1,5 → 1,0 | Nenhuma perturbação precisou de tolerância maior. |
| `SUMMARY_TOLERANCES`: CH₄ e biogás finais | 5% → 0,01% | Paridade final observada muito melhor que 0,01%. |
| `SUMMARY_TOLERANCES`: VFA e DQO finais | 10% → 0,01% | Mesmo motivo; maior erro atual de VFA ≈0,000002%. |
| `SUMMARY_TOLERANCES`: pH | 0,1 → 1e-5 absoluto | Convergência do equilíbrio ácido-base e erro observado. |
| `SUMMARY_TOLERANCES`: fração CH₄ | 0,05 → 1e-5 absoluto | Frações finais coincidem numericamente. |
| `SUMMARY_TOLERANCES`: CH₄ acumulado | 5% → 0,5% | Diferença de convenção no ponto inicial, máximo 0,392605%. |
| `SERIES_TOLERANCES`: gases | NRMSE 5% → 0,01% | O primeiro ponto continua excluído, explicitamente. |
| `SERIES_TOLERANCES`: VFA e DQO | NRMSE 10% → 0,01% | Maior NRMSE de todas as séries: 0,0000225355%. |
| `SERIES_TOLERANCES`: pH | RMSE 0,05 → 1e-5 | Mesmo equilíbrio nos dois backends. |
| `test_full_parity_baseline_passes_gates` | CH₄ final <0,1% → <0,01%; NRMSE CH₄ <1% → <0,01% | Alinha as asserções específicas aos gates gerais. |
| `TestMicroalgaeLiteratureValidation.test_nitrogen_balance_in_disintegration` | `rel=0.05` → `rel=1e-12, abs=1e-14` | É uma identidade estequiométrica algébrica, não dado experimental com incerteza de 5%. |

Rastreabilidade das mudanças anteriores: PR #6 (`0ff8614`, merge `82b6961`)
tornou a alimentação/inicialização absolutas e corrigiu dupla contagem de VFA.
PR #7 (`ceadf7e`, merge `b8ae447`) tornou absoluto o mapeamento da alcalinidade
legada para S_IC e resolveu pH/H₂ a cada RHS do PyADM1. Ambos afetam os cenários
com `FeedDefinition`; a entrada ADM1 explícita das Tabelas 5/6 é preservada.
Os PRs seguintes, até #20, estão incluídos na presente medição. Não se atribui
uma diferença agregada inteira a um único PR sem executar um contrafactual.
README e textos do webapp consultados não contêm uma tabela fixa de saídas
BSM2/benchmark que precise ser substituída; a UI usa relatórios gerados.
O webapp não foi alterado.

Os quatro CLIs de validação/benchmark/paridade usavam `str(output_dir)` e
expunham caminhos absolutos. Agora usam `_safe_project_path`. A conclusão textual
BSM2 passou a respeitar o campo `validated`, em vez de sempre afirmar sucesso.
Essas duas correções de relatório têm testes que falharam antes e passam depois.

## Falhas, limites e pendências

1. **PyADM1/BDF, 400 dias e 201 pontos (corrigido):** a execução com rtol=1e-10 e
   atol=1e-12 falhava com `PyADM1 hydrogen balance did not converge`. Reproduzida
   com o código anterior (falha após ~110 s). Causa: o Jacobiano numérico do SciPy
   (`_ivp/common.py`, perturbação do passo) estourou (`overflow`), o estado virou
   `inf`/`NaN` e os Newton do patch de runtime (H⁺ e S_h2) compararam `NaN` com a
   tolerância, sem convergir; o patch então levantava o erro e abortava a integração
   em vez de deixar o integrador rejeitar o passo. Correção: `simulator/core/algebraic.py`
   (`bracketed_newton`: Newton com intervalo de troca de sinal e bisecção) usado para
   H⁺ em [1e-14, 1] e S_h2 em [0, S_h2 máximo físico]; estado não finito devolve
   derivadas `NaN` (o integrador reduz o passo); não convergência em estado finito
   continua levantando erro. O mesmo Newton do modelo completo
   (`full_model/acid_base.py`) ganhou o intervalo e a bisecção como fallback, sem
   alterar o resultado quando o Newton simples converge. Resultado: 400 dias/201
   pontos e 400 dias/401 pontos (BDF, tolerâncias acima) concluem em poucos
   segundos, com erro máximo de 1,04e-6 % contra o estado estacionário BSM2
   publicado (limite 0,1 %) e igual ao modelo completo. Em 200 dias, a diferença
   contra o código anterior é de até 3,4e-9 em valor relativo (ruído do integrador
   BDF; as funções algébricas coincidem a 7e-15). Testes:
   `simulator/tests/test_pyadm1_algebraic_robustness.py`.
2. **ODE completa:** a versão puramente diferencial ácido-base do relatório não
   é um backend atual. Esta auditoria valida as formulações DAE1/DAE2 existentes.
3. **Validação reduced BSM2:** o comando existente retorna erro relativo máximo
   próximo de 100% e `validated=false`. Além da estrutura simplificada, sua
   aproximação ainda passa S_IC/HCO₃ em kmol/m³ diretamente à escala legada de
   alcalinidade, cujo fator é 17 mol/m³ por unidade; soma `X_pro` aos acidogênicos
   e mantém `propionate_biomass` no default, e agrupa material inerte no substrato
   degradável. Essa aproximação não é referência científica. Corrigir esse
   mapeamento exige definir uma agregação coerente; não se recalibrou o reduced
   nem se usaram seus valores para aprovar BSM2.
4. **OpenModelica:** ferramenta ausente e fluxo efetivo de comparação externa
   ainda não implementado neste comando.
5. A aprovação é do CSTR mesofílico com cinética BSM2 padrão e das seis perturbações
   de paridade; não demonstra validade de extensões, dados de planta ou dimensionamento
   de outros reatores. Os demais testes de literatura das extensões foram executados.

## Testes

- Antes das mudanças: **37 passaram em 48,37 s** nos seis arquivos de literatura/
  paridade listados nos comandos.
- Regressão dos gates: duas falhas antes do aperto, pois 1% de erro era aceito.
- Regressão de relatórios: cinco falhas antes das correções (quatro caminhos
  absolutos e uma conclusão de sucesso para comparação reprovada).
- Novos testes publicados/relatório: **22 passaram em 13,11 s**.
- `.venv/bin/python -m pytest simulator/tests -q`: **767 passaram, 1 excluído
  pelo marcador `slow`, em 226,98 s (3 min 47 s)**. Nenhuma falha ou skip.
- `git diff --check`: sem erros.
- Não houve alteração no webapp; sua suíte não é necessária por esta tarefa.
