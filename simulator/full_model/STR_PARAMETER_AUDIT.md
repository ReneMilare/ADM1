# Auditoria dos parâmetros do núcleo ADM1 frente ao STR e ao BSM2

## Fontes, escopo e convenções

- Batstone et al. (2002), *Anaerobic Digestion Model No. 1*, IWA STR 13, [DOI 10.2166/9781780403052](https://doi.org/10.2166/9781780403052), Tabelas 2.6, 3.1, 3.2, 3.5, 4.1, 4.2, 6.1, 6.2 e Apêndice B. A Tabela 6.2 foi conferida visualmente no PDF, além da extração com `pdftotext -layout`.
- Rosén e Jeppsson (2006), *Aspects on ADM1 Implementation within the BSM2 Framework*, §§ 3.1–3.2 e 6, inclusive tabelas de parâmetros. PyADM1 é usado apenas para verificar a implementação adotada, não como fonte primária.
- A coluna mesofílica usa a coluna **solids, nominal 35 °C** da Tabela 6.2; a termofílica usa **solids, nominal 55 °C**. Valores são recomendações para substratos/sistemas, não constantes universais. `M = kmol/m³`; C e N em kmol/kgDQO; taxas em d⁻¹; constantes de substrato e inibição de H₂ em kgDQO/m³; frações e rendimentos são adimensionais. Nas constantes físico-químicas informamos unidades na própria tabela.
- “Igual”: os três concordam; “BSM2”: desvio explicado/adotado no BSM2; “escolha BSM2”: STR não fixa o valor; “ambíguo”: não foi possível determinar intenção ou justificativa. Os valores no código são os padrões, antes de calibração, de overrides e da correção opcional de Siegrist. `parameter_set=thermophilic_str` muda apenas os valores termofílicos listados. Nenhum número da Tabela 6.1 é automaticamente específico de 55 °C.
- O catálogo contém também `f_lac_su`, `f_et_su`, `C_lac` e `C_et`, que pertencem às extensões lactato/etanol e não ao núcleo STR/BSM2; os dois primeiros são zero por padrão. Valores de referência operacionais e tolerâncias de solver não são parâmetros bioquímicos universais, mas são listados abaixo.

## Estequiometria e cinética

A Tabela 2.6 do STR informa valores variáveis para C de inertes, proteínas e aminoácidos; não se deve atribuir a ela os números adotados pelo BSM2. A Tabela 6.1 dá frações e nitrogênio de compostos; a 6.2 dá rendimentos e cinética. A primeira coluna identifica o nome no código.

| Parâmetro | Código mesofílico | STR mesofílico | BSM2 | STR 55 °C | Avaliação |
|---|---:|---:|---:|---:|---|
| `f_sI_xc` | 0,1 | 0,1 | 0,1 | — | igual |
| `f_xI_xc` | 0,2 | 0,25 | 0,2 | — | BSM2 (§3.1.1/§6) |
| `f_ch_xc` | 0,2 | 0,2 | 0,2 | — | igual |
| `f_pr_xc` | 0,2 | 0,2 | 0,2 | — | igual |
| `f_li_xc` | 0,3 | 0,25 | 0,3 | — | BSM2 (§3.1.1/§6) |
| `N_xc` | 0,0376/14 | 0,002 | 0,0376/14 | — | BSM2 (§3.1.1/§6) |
| `N_I` | 0,06/14 | 0,002 | 0,06/14 | — | BSM2 (§3.1.1/§6) |
| `N_aa` | 0,007 | 0,007 | 0,007 | — | igual |
| `C_xc` | 0,02786 | variável; 0,03 na implementação original citada no BSM2 | 0,02786 | — | BSM2 (§3.1.1/§6) |
| `C_sI` | 0,03 | variável | 0,03 | — | escolha BSM2 (§6) |
| `C_ch` | 0,0313 | 0,0313 | 0,0313 | — | igual |
| `C_pr` | 0,03 | variável | 0,03 | — | escolha BSM2 (§6) |
| `C_li` | 0,022 | 0,022 | 0,022 | — | igual |
| `C_xI` | 0,03 | variável | 0,03 | — | escolha BSM2 (§6) |
| `C_su` | 0,0313 | 0,0313 | 0,0313 | — | igual |
| `C_aa` | 0,03 | variável | 0,03 | — | escolha BSM2 (§6) |
| `f_fa_li` | 0,95 | 0,95 | 0,95 | — | igual |
| `C_fa` | 0,0217 | 0,0217 | 0,0217 | — | igual |
| `f_h2_su` | 0,19 | 0,19 | 0,19 | — | igual |
| `f_bu_su` | 0,13 | 0,13 | 0,13 | — | igual |
| `f_pro_su` | 0,27 | 0,27 | 0,27 | — | igual |
| `f_ac_su` | 0,41 | 0,41 | 0,41 | — | igual |
| `N_bac` | 0,08/14 | 0,00625 | 0,08/14 | — | BSM2 (§3.1.1/§6) |
| `C_bu` | 0,025 | 0,025 | 0,025 | — | igual |
| `C_pro` | 0,0268 | 0,0268 | 0,0268 | — | igual |
| `C_ac` | 0,0313 | 0,0313 | 0,0313 | — | igual |
| `C_bac` | 0,0313 | 0,0313 | 0,0313 | — | igual |
| `Y_su` | 0,1 | 0,1 | 0,1 | 0,1 | igual |
| `f_h2_aa` | 0,06 | 0,06 | 0,06 | — | igual |
| `f_va_aa` | 0,23 | 0,23 | 0,23 | — | igual |
| `f_bu_aa` | 0,26 | 0,26 | 0,26 | — | igual |
| `f_pro_aa` | 0,05 | 0,05 | 0,05 | — | igual |
| `f_ac_aa` | 0,4 | 0,4 | 0,4 | — | igual |
| `C_va` | 0,024 | 0,024 | 0,024 | — | igual |
| `Y_aa` | 0,08 | 0,08 | 0,08 | 0,08 | igual |
| `Y_fa` | 0,06 | 0,06 | 0,06 | 0,06 | igual |
| `Y_c4` | 0,06 | 0,06 | 0,06 | 0,06 | igual |
| `Y_pro` | 0,04 | 0,04 | 0,04 | 0,05 | igual |
| `C_ch4` | 0,0156 | 0,0156 | 0,0156 | — | igual |
| `Y_ac` | 0,05 | 0,05 | 0,05 | 0,05 | igual |
| `Y_h2` | 0,06 | 0,06 | 0,06 | 0,06 | igual |
| `k_dis` | 0,5 | 0,5 | 0,5 | 1 | igual |
| `k_hyd_ch` | 10 | 10 | 10 | 10 | igual |
| `k_hyd_pr` | 10 | 10 | 10 | 10 | igual |
| `k_hyd_li` | 10 | 10 | 10 | 10 | igual |
| `K_S_IN` | 0,0001 | 0,0001 | 0,0001 | 0,0001 | igual |
| `k_m_su` | 30 | 30 | 30 | 70 | igual |
| `K_S_su` | 0,5 | 0,5 | 0,5 | 1 | igual |
| `pH_UL_aa` | 5,5 | 5,5 | 5,5 | 5,5 | limites iguais; forma BSM2 (§3.2.2) |
| `pH_LL_aa` | 4 | 4 | 4 | 4 | limites iguais; forma BSM2 (§3.2.2) |
| `k_m_aa` | 50 | 50 | 50 | 70 | igual |
| `K_S_aa` | 0,3 | 0,3 | 0,3 | 0,3 | igual |
| `k_m_fa` | 6 | 6 | 6 | 10 | igual |
| `K_S_fa` | 0,4 | 0,4 | 0,4 | 0,4 | igual |
| `K_I_h2_fa` | 5e-06 | 5e-06 | 5e-06 | n/a | mesofílico igual; 55 °C ambíguo |
| `k_m_c4` | 20 | 20 | 20 | 30 | igual |
| `K_S_c4` | 0,2 | 0,2 | 0,2 | 0,4 | igual |
| `K_I_h2_c4` | 1e-05 | 1e-05 | 1e-05 | 3e-05 | igual |
| `k_m_pro` | 13 | 13 | 13 | 20 | igual |
| `K_S_pro` | 0,1 | 0,1 | 0,1 | 0,3 | igual |
| `K_I_h2_pro` | 3,5e-06 | 3,5e-06 | 3,5e-06 | 1e-05 | igual |
| `k_m_ac` | 8 | 8 | 8 | 16 | igual |
| `K_S_ac` | 0,15 | 0,15 | 0,15 | 0,3 | igual |
| `K_I_nh3` | 0,0018 | 0,0018 | 0,0018 | 0,011 | igual |
| `pH_UL_ac` | 7 | 7 | 7 | 7 | limites iguais; forma BSM2 (§3.2.2) |
| `pH_LL_ac` | 6 | 6 | 6 | 6 | limites iguais; forma BSM2 (§3.2.2) |
| `k_m_h2` | 35 | 35 | 35 | 35 | igual |
| `K_S_h2` | 7e-06 | 7e-06 | 7e-06 | 5e-05 | igual |
| `pH_UL_h2` | 6 | 6 | 6 | 6 | limites iguais; forma BSM2 (§3.2.2) |
| `pH_LL_h2` | 5 | 5 | 5 | 5 | limites iguais; forma BSM2 (§3.2.2) |
| `k_dec_X_su` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_aa` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_fa` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_c4` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_pro` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_ac` | 0,02 | 0,02 | 0,02 | 0,04 | igual |
| `k_dec_X_h2` | 0,02 | 0,02 | 0,02 | 0,04 | igual |

O STR usa “n/a” para `K_I_h2_fa` em 55 °C: pode significar ausência de valor ou inaplicabilidade da inibição. O conjunto opcional preserva provisoriamente a inibição BSM2 (5×10⁻⁶), sem apresentar esse número como dado termofílico. Use override fundamentado em dados locais; essa escolha pode alterar substancialmente o consumo de LCFA.

`N_bac` é 0,08/14 ≈ 0,005714 no BSM2 versus 0,00625 no STR. O STR informa `C_xc` como variável na Tabela 2.6; Rosén e Jeppsson relatam 0,03 na implementação ADM1 original e adotam 0,02786 para aproximar o C dos produtos. As modificações de `f_xI_xc`, `f_li_xc`, `N_I` e `N_xc` são explicadas em §3.1.1, para compatibilidade ASM e balanço de N. Os respectivos parâmetros têm essa proveniência em `notes` do catálogo.

## Constantes físico-químicas e operacionais

Na tabela, `E(H) = exp[H/(100 R) × (1/T_base − 1/T)]`, com H em J/mol e `R = 0,083145 bar·m³/(kmol·K)`; multiplicar R por 100 converte para J/(mol·K). `K0` se refere a 298,15 K no código/BSM2, enquanto o STR arredonda a temperatura de referência para 298 K. Os expoentes e sinais de ΔH são idênticos. As constantes são recalculadas à temperatura de operação, inclusive no conjunto termofílico.

| Parâmetro | Código | STR | BSM2 | Avaliação |
|---|---|---|---|---|
| `R` | 0,083145 bar·m³/(kmol·K) | constante universal | 0,083145 | igual |
| `T_base` | 298,15 K | 298 K (arredondado) | 298,15 K | convenção BSM2 |
| `T_op`, `T_ad` | 308,15 K no catálogo; temperatura operacional no runtime | 35 °C mesofílico ou 55 °C termofílico nominal | 308,15 K no benchmark | condição operacional |
| `K_w` | 10⁻¹⁴ E(55900), M² | pKw 14,00; ΔH 55900 | mesma expressão | igual, com referência de temperatura BSM2 |
| `K_a_va` | 10⁻⁴·⁸⁶ M | pKa 4,86 | 10⁻⁴·⁸⁶ | igual |
| `K_a_bu` | 10⁻⁴·⁸² M | pKa 4,82 | 10⁻⁴·⁸² | igual |
| `K_a_pro` | 10⁻⁴·⁸⁸ M | pKa 4,88 | 10⁻⁴·⁸⁸ | igual |
| `K_a_ac` | 10⁻⁴·⁷⁶ M | pKa 4,76 | 10⁻⁴·⁷⁶ | igual |
| `K_a_co2` | 10⁻⁶·³⁵ E(7646), M | pKa 6,35; ΔH 7646 | mesma expressão | igual, com referência de temperatura BSM2 |
| `K_a_IN` | 10⁻⁹·²⁵ E(51965), M | pKa 9,25; ΔH 51965 | mesma expressão | igual, com referência de temperatura BSM2 |
| `k_A_B_va`, `k_A_B_bu`, `k_A_B_pro`, `k_A_B_ac`, `k_A_B_co2`, `k_A_B_IN` | 10¹⁰ M⁻¹·d⁻¹ cada | 10⁸, Apêndice B | 10¹⁰ | BSM2 §3.1.2 acelera ODE; não usado no equilíbrio algébrico |
| `K_H_h2` | 7,8×10⁻⁴ E(−4180), M/bar | mesmo K0 e ΔH | mesma expressão | igual |
| `K_H_ch4` | 0,0014 E(−14240), M/bar | mesmo K0 e ΔH | mesma expressão | igual; o sobrescrito 3 da Tabela 4.2 é nota, não dígito |
| `K_H_co2` | 0,035 E(−19410), M/bar | mesmo K0 e ΔH | mesma expressão | igual |
| `p_gas_h2o` | 0,0313 exp[5290(1/T_base − 1/T)] bar | mesmo fator; ΔH vaporização 43980 J/mol, Eq. 5.7 | mesma expressão | igual com referência BSM2 |
| `k_L_a` | 200 d⁻¹; escalável por configuração | variável por mistura e condições; §4.2 | 200 | escolha BSM2 |
| `k_p` | 50000 m³/(d·bar) | dependente da válvula; §5.2 | 50000 | escolha BSM2 |
| `p_atm` | catálogo 1,01325 bar; runtime 1,013 | pressão da instalação | 1,013 bar | runtime igual BSM2; catálogo usa 1 atm exata |
| `V_liq`, `V_gas`, `V_ad` | catálogo 3400, 300, 3700 m³; runtime depende da configuração | valores de projeto | 3400, 300, 3700 m³ | condições BSM2, não propriedades universais |
| `q_ad` | catálogo 170 m³/d; runtime depende da alimentação | valor de projeto | 170 m³/d | condição BSM2 |
| `K_pH_aa`, `K_pH_ac`, `K_pH_h2` | 10⁻⁴·⁷⁵, 10⁻⁶·⁵, 10⁻⁵·⁵ M | sem constante Hill em [H⁺] | ponto médio 10⁻⁽ᵁᴸ⁺ᴸᴸ⁾/² | BSM2 §3.2.2; derivado dos limites |
| `nn_aa`, `n_ac`, `n_h2` | 2, 3, 3 | função pH original sem expoente Hill | 3/(UL−LL) | BSM2 §3.2.2; derivado dos limites |
| `ph_solver_tol`, `hydrogen_solver_tol`, `max_newton_iterations` | 10⁻¹², 10⁻¹², 1000 | controles numéricos não universais | controles de implementação | controles locais |

Os ácidos orgânicos mantêm Ka constante, conforme BSM2 §3.1.3 e STR §4.3: o STR não fornece um ΔH constante adequado para o intervalo. H₂S e fosfato são extensões e não integram o núcleo auditado.

## Matriz, taxas e inibições

A Tabela 3.1 do STR cobre as colunas solúveis e a 3.2 as particuladas. Conferência das 19 linhas, com `b = 1 − Y` em cada linha de uptake:

| Processo | Coeficientes DQO da matriz e taxa | Avaliação |
|---|---|---|
| 1 desintegração | `−X_xc`, `+f_sI S_I + f_ch X_ch + f_pr X_pr + f_li X_li + f_xI X_I`; `k_dis X_xc` | STR e frações BSM2 |
| 2–4 hidrólises | `−X_ch + S_su`; `−X_pr + S_aa`; `−X_li + (1−f_fa) S_su + f_fa S_fa`; `k_hyd X` | igual |
| 5 açúcar | `−S_su + b(f_bu S_bu + f_pro S_pro + f_ac S_ac + f_h2 S_h2) + Y_su X_su` | igual sem extensões; Monod × I₅ |
| 6 aminoácidos | `−S_aa + b(f_va S_va + f_bu S_bu + f_pro S_pro + f_ac S_ac + f_h2 S_h2) + Y_aa X_aa` | igual; Monod × I₆ |
| 7 LCFA | `−S_fa + b(0,70 S_ac + 0,30 S_h2) + Y_fa X_fa` | igual; Monod × I₇ |
| 8 valerato | `−S_va + b(0,54 S_pro + 0,31 S_ac + 0,15 S_h2) + Y_c4 X_c4` | igual; Monod × competição C4 × I₈ |
| 9 butirato | `−S_bu + b(0,80 S_ac + 0,20 S_h2) + Y_c4 X_c4` | igual; Monod × competição C4 × I₉ |
| 10 propionato | `−S_pro + b(0,57 S_ac + 0,43 S_h2) + Y_pro X_pro` | igual; Monod × I₁₀ |
| 11 acetato | `−S_ac + b S_ch4 + Y_ac X_ac` | igual; Monod × I₁₁ |
| 12 hidrogênio | `−S_h2 + b S_ch4 + Y_h2 X_h2` | igual; Monod × I₁₂ |
| 13–19 decaimentos | `−X_grupo + X_xc`; `k_dec,grupo X_grupo` | igual para as sete biomassas |

Os termos `S_IC = −Σ(C_i ν_i,j)` e `S_IN` adicionais seguem BSM2 §3.1.1 para fechar C e N em todas as linhas, inclusive desintegração, hidrólises e decaimentos. O STR deixa esses termos ausentes em várias linhas; adotar literalmente seus zeros destruiria a conservação. A fermentação de açúcar ajusta as frações quando as extensões lactato/etanol estão ativas; sem elas, as equações acima são as originais. Os testes verificam todos os 19 processos por DQO, C e N, nos dois conjuntos.

As taxas de uptake usam `k_m S/(K_S+S) X`; C4 usa `S_va/(S_va+S_bu+10⁻⁶)` ou `S_bu/(...)`. O STR usa as razões equivalentes sem 10⁻⁶; BSM2 §3.2.1 acrescenta o termo para evitar divisão por zero. Os fatores são `I₅=I₆=I_pH,aa I_IN`, `I₇=I₅ I_H2,fa`, `I₈=I₉=I₅ I_H2,c4`, `I₁₀=I₅ I_H2,pro`, `I₁₁=I_pH,ac I_IN I_NH3`, `I₁₂=I_pH,h2 I_IN`; `I_IN=S_IN/(K_S_IN+S_IN)` e `I_H2`, `I_NH3=1/(1+S/K_I)`. O código aplicava H₂ mínimo de 10⁻¹² mesmo quando zero; isso foi corrigido e coberto por teste que falhava antes. Em concentrações negativas, a entrada continua truncada em zero.

O STR Tabela 3.5 usa uma forma exponencial por partes para baixo pH; BSM2 §3.2.2 escolhe uma função Hill suave em H⁺ com os mesmos limites. É desvio de formulação deliberado, não igualdade ponto a ponto. As relações ácido-base algébricas usam as frações dissociadas e balanço de carga conforme STR §4.1 e BSM2 §4.2; a transferência usa CO₂ livre e fatores 16 e 64 para H₂ e CH₄ conforme STR Eq. 5.4. A vazão de gás positiva por diferença de pressão segue BSM2; a saturação e as limitações numéricas são escolhas de implementação.

## Uso e precedência do conjunto termofílico

`KineticParameters(parameter_set="thermophilic_str")` seleciona os valores cinéticos termofílicos da tabela no backend `full`; o padrão é `mesophilic_bsm2`. A temperatura física continua sendo informada separadamente em `OperatingConditions(temperature_c=55)`: selecioná-lo não muda a temperatura do reator. A correção bioquímica `temperature_kinetics="siegrist2002"` é ignorada para o conjunto termofílico, evitando dupla correção; os ajustes físico-químicos por temperatura continuam ativos. Em TPAD, o mesmo conjunto termofílico fixo é aplicado às duas fases, inclusive a 35 °C; não há troca automática de população ou conjunto entre fases. Essa é uma simplificação e não substitui parâmetros específicos para cada fase. Overrides explícitos em `full_extension_parameter_overrides` prevalecem; os campos cinéticos existentes escalam os valores do conjunto pela razão frente aos seus defaults. O backend reduzido ou PyADM1 rejeita explicitamente o novo conjunto para evitar que ele seja ignorado silenciosamente. Os metadados registram seleção, modo solicitado e modo efetivo.

## Limites da auditoria

Os valores padrão em STR/BSM2 são pontos iniciais e podem exigir calibração para substrato e regime. `K_I_h2_fa` a 55 °C permanece indeterminado; a validade preditiva do conjunto termofílico para uma instalação concreta não foi estabelecida. A auditoria não revisa as extensões nem o modelo reduzido. A paridade com PyADM1 se aplica ao conjunto mesofílico de referência, não valida a física termofílica.
