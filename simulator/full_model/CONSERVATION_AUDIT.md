# Correções da auditoria de conservação

A correção mantém a extensão `trace_elements` utilizável sem `srb`. Sem o estado
`S_H2S`, as seis taxas de precipitação e dissolução de NiS, CoS e FeS são zero.
Os sulfetos iniciais ficam inertes. A complexação, a limitação por metais e as
reações de FeCO3 continuam disponíveis. Isso evita criar ou remover enxofre sem
um reservatório dissolvido, conforme as reações de Maharaj et al. (2018),
Tabela 1, DOI: 10.1016/j.biortech.2018.06.099. Com `srb`, a dissolução devolve
enxofre a `S_H2S`, inclusive quando sua concentração inicial é zero.

A incompatibilidade entre `iron` e `trace_elements` permanece. As duas extensões
representam Fe(II) e precipitação/dissolução do mesmo mineral FeS em reservatórios
independentes (`S_Fe2`/`X_FeS` e `S_Fe2_te`/`X_FeS_te`). A mensagem de validação
explica essa duplicação. A combinação sem `phosphorus` também carece de `S_IP`:
nesse caso a validação estrutural informa primeiro o estado ausente.

O coeficiente de acetato produzido pela oxidação SRB de propionato passa de
`0.5714` para `4/7 = 64/112`. As frações do etanol passam de `0.6667` e `0.3333`
para `2/3` e `1/3`. Os conteúdos de carbono de fenol e benzoato usam `6/224` e
`7/240`, em vez de `0.02679` e `0.02917`. A revisão das expressões estequiométricas
das extensões não encontrou outros quocientes químicos arredondados. Valores
medidos ou calibrados, como os rendimentos SRB, e o catálogo canônico do núcleo
ADM1 permanecem como publicados; eles não são aproximações desses quocientes.

Os proxies do catálogo agora usam `C_lac`, `C_et`, `C_phen`, `C_ben` e `C_CO`
nos respectivos substratos. `C_CO = 1/16` também aparece nas reações. Os
carbonatos sólidos declaram um mol C por mol. A desintegração de microalgas
usa `C_sI` para `S_I` e `C_xI` para `X_I`. O teste de regressão usa conteúdos
distintos para esses dois inertes, conforme o contraexemplo da auditoria.

O balanço eletrônico do ferro usa Fe(III) como referência. Fe(II) armazena um
elétron por mol, equivalente a 8 kgO2/kmol Fe. Portanto, o inventário inclui
8 em `S_Fe2`, 8 mais 64 do sulfeto em `X_FeS`, 24 em `X_VIV` e 48 em `X_S0`.
Esse balanço fecha mesmo com Fe(III) fixo. A massa total de ferro continua sendo
um balanço aberto. Base: Lizarralde et al. (2015), DOI:
10.1016/j.watres.2015.01.031. A DQO apenas orgânica não é conservada quando
transfere elétrons ao enxofre ou ao ferro.

As extensões lactate, ethanol, srb, syngas, lcfa_adsorption e multi_population
agora calculam a limitação por N como `S_IN/(K_S_IN + S_IN)`, com `S_IN >= 0`.
Phenolics já usava essa forma. Os testes verificam taxa de síntese de biomassa
exatamente zero com N nulo ou negativo e retomada com N disponível. Base:
Batstone et al. (2002), ADM1, fator de limitação por nitrogênio inorgânico.

## Interface ASM1 → ADM1

A fonte convertida de Nopens et al. (2009), DOI:
10.1016/j.watres.2009.01.012, estava disponível para consulta. A seção 2,
passo 1, informa a remoção dos aceptores usando os doadores na ordem `S_S`,
`X_S`, `X_BH`, `X_BA`. A implementação usa os fatores de engenharia padrão
1 gDQO/gO2 e 2,86 gDQO/gN-NO3. Não aplica crescimento nessa remoção instantânea.
O campo opcional `S_O`, padrão zero, preserva chamadas anteriores.

A oxidação da biomassa libera seu N orgânico no reservatório de amônia.
`S_ND` e `X_ND` continuam disponíveis para a distribuição do N. O verificador
compara a DQO de entrada com a soma de DQO convertida e oxidada. Compara o N
total de entrada, incluindo nitrato, com o N ADM1 mais o N2 exportado.
`n2_lost_kmol_n_m3` expressa kmol de átomos N por m³; a concentração molar de
N2 correspondente é metade desse valor. O MCP expõe esses resultados.

A desnitrificação acrescenta um equivalente de alcalinidade por mol N-NO3.
Os íons fortes são recalculados para eletroneutralidade a pH nominal 7 e
35 °C, com um dos dois reservatórios igual a zero, seguindo a escolha da
seção 4.2 de Nopens. Água sem pools inorgânicos mantém íons fortes nulos e
pH neutro natural. `S_IC` continua sendo um proxy da alcalinidade, não uma
medição independente de carbono total. A interface ainda não demonstra um
balanço elementar completo de C entre ASM1 e ADM1.

NOx é tratado como nitrato: não há separação de nitrito. A interface rejeita
entradas não finitas ou negativas. Também rejeita DQO biodegradável insuficiente
para remover os aceptores, pois o ADM1 não possui estados para reter O2/NO3.

## Verificação

Os novos testes reproduziram as falhas antes das correções. Um teste antigo
teve sua expectativa corrigida: em
`TestTraceElementsExtension.test_dissolution_rates_positive_when_precipitates_present`,
as taxas de dissolução de NiS, CoS e FeS sem `srb` passaram de `> 0` para `== 0`,
pois não há pool dissolvido que receba o enxofre. O teste agora se chama
`test_dissolution_rates_follow_available_sulfide_pool` e cobre ambos os
assemblies. Com `srb`, as taxas continuam positivas. FeCO3 continua positivo
em ambos. Nenhuma outra expectativa antiga foi alterada.
As verificações de batelada integram
também a saída gasosa e usam os volumes de líquido e headspace no inventário.
As matrizes usam o mesmo ajuste de volume nas colunas de transferência gasosa.

As colunas de sulfetos de E9 sem SRB e as quatro colunas substituídas por
multi_population permanecem na matriz, mas têm taxas identicamente nulas.
O relatório estequiométrico conserva seus resíduos brutos e as marca como
inativas; elas não representam perda dinâmica de massa.

Os inventários de S e P cobrem apenas os pools com composição especificada.
O modelo não define conteúdo orgânico completo desses elementos. Os ensaios
dinâmicos verificam as EDOs dos compartimentos diretamente, com quadraturas de
entrada, saída líquida e gás; não verificam o truncamento de perfis do solver
público. As condições testadas não constituem prova para toda parametrização.

## Resultados antes e depois

A auditoria repetiu 816 integrações de conservação e 96 verificações adicionais
do catálogo de carbono: 17 assemblies válidos, seis modos e três condições
térmicas, com e sem vazão e pulso de NH4Cl. As 912 integrações terminaram sem
erros, em 513 s. As tolerâncias permaneceram BDF `rtol=2e-9`, `atol=1e-12`,
com duração de 0,25 d e passo máximo de 0,0125 d. A tabela consolidada mantém
726 linhas. Os scripts de conferência ficaram fora do repositório.

Cada linha abaixo mostra o maior resíduo relativo sobre os casos ensaiados.

| Combinação | Grandeza | Antes | Depois |
|---|---|---:|---:|
| trace_elements | S | 2,191660e-1 | 2,652413e-15 |
| trace_elements | DQO | 2,343429e-6 | 6,987706e-16 |
| srb | DQO | 1,326679e-6 | 7,148293e-16 |
| srb + trace_elements | DQO | 1,135850e-6 | 9,292782e-16 |
| phenolics + syngas + srb + multi_population | DQO | 1,122400e-6 | 3,055009e-15 |
| srb + phosphorus + iron | DQO com Fe(II) | 1,580212e-6 | 3,157030e-14 |
| lactate | C pelo catálogo | 2,255494e-5 | 2,943903e-15 |
| lactate + ethanol | C pelo catálogo | 2,196074e-5 | 1,486459e-13 |
| ASM municipal | N total, incluindo N2 exportado | 7,575758e-2 | 1,839858e-16 |
| Microalgas, C_sI=0,04 e C_xI=0,03 | C na coluna de desintegração | 3,47548e-3 | 6,008116e-17 |

O maior resíduo nas colunas ativas de DQO de SRB, incluindo transferência
gasosa, foi `1,11e-16`. A coluna SRB de propionato ficou em `4,86e-17`.
Não houve anomalias acima de `1e-12` nas colunas ativas de C, N, S, P ou DQO
com Fe(II) em nenhum assembly montável da auditoria estequiométrica.

O resíduo dinâmico de C de `lactate + ethanol` acumulou erro numérico em
batelada a 25 °C: a derivada inicial do balanço foi zero e os estados ficaram
positivos. Uma conferência adicional com `rtol=2e-11`, `atol=1e-14` reduziu esse
resíduo de `1,49e-13` para `1,85e-17`. No pior caso do ferro, a DQO com Fe(II)
caiu de `3,16e-14` para `2,70e-16`. Esses resultados de refinamento não
substituem os valores da tabela, calculados com as tolerâncias originais.

O máximo global, nas tolerâncias originais, foi `1,49e-13` para C,
`4,04e-14` para N, `1,67e-13` para S, `2,50e-15` para P e `2,35e-13` para
DQO com Fe(II). A DQO sem Fe(II) continua com resíduo de `4,30e-4` no caso
com ferro, conforme a referência de equivalentes descrita acima.

Na amostragem ASM, 930 dos 1.001 vetores originais tinham doadores suficientes.
Os outros 71 foram rejeitados explicitamente. Nos 930 convertidos, os erros
máximos relativos foram `4,34e-16` para DQO com a parcela oxidada e `4,45e-16`
para N com N2. O caso municipal oxida `0,0143 kgDQO/m³` e exporta
`3,571429e-4 kmolN/m³` como N2. A repetição independente da eletroneutralidade
concluiu 192 integrações e 576 pontos, sem falha de convergência: máximo
absoluto `9,53e-13 kmol de carga/m³`, relativo `1,36e-11`.

## Comandos e arquivos

Verificação final da suíte completa, com uma thread por biblioteca numérica:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest simulator/tests -q
```

Resultado: **745 passed, 1 deselected**, em **138,45 s**. A primeira execução
completa encontrou apenas o teste antigo de dissolução descrito acima
(`743 passed, 1 failed, 1 deselected`). Após atualizar essa expectativa e
acrescentar o caso com SRB, a execução final passou. O webapp não foi alterado.

Os scripts copiados da auditoria C executaram `rerun.py`,
`stoich/run_stoich.py`, `compile_results.py`, `compare.py`,
`pulse/audit_asm.py`, `review/check_charge.py`,
`review/microalgae_override.py` e `refine.py`, sempre com o Python da `.venv`.
O bundle externo `adm1-audit-e` contém os scripts adaptados, manifesto,
JSONL, CSVs, logs e instruções de reprodução. A versão original
`adm1-audit-c` foi preservada.

Mapa das mudanças, com linhas de referência desta revisão:

| Arquivo | Linha | Mudança |
|---|---:|---|
| trace_elements_extension.py | 540 | Inativação de sulfetos sem pool dissolvido |
| trace_elements_extension.py | 665 | Motivo da incompatibilidade de FeS |
| srb_extension.py | 567 | Quociente estequiométrico 4/7 |
| ethanol_extension.py | 164 | Frações 2/3 e 1/3; proxy C_et na linha 63 |
| phenolics_extension.py | 231 | Conteúdos de C exatos; proxies nas linhas 88 e 100 |
| lactate_extension.py | 70 | Proxy C_lac |
| syngas_extension.py | 205 | C_CO derivado, usado nos proxies e reações |
| phosphorus_extension.py | 114 | Carbono explícito de CaCO3 |
| trace_elements_extension.py | 131 | Carbono explícito de FeCO3 |
| microalgae_extension.py | 252 | Separação de C_sI e C_xI |
| iron_extension.py | 28 | Referência de equivalentes redutores de Fe(II) |
| lactate_extension.py | 259 | Limitação de N sem piso positivo |
| ethanol_extension.py | 229 | Limitação de N sem piso positivo |
| srb_extension.py | 631 | Limitação de N sem piso positivo |
| syngas_extension.py | 449 | Limitação de N sem piso positivo |
| lcfa_extension.py | 258 | Limitação de N sem piso positivo |
| multi_population_extension.py | 484 | Limitação de N sem piso positivo |
| asm_adm1_interface.py | 77 | Remoção de aceptores e liberação de N |
| asm_adm1_interface.py | 198 | Balanço com DQO oxidada e N2 exportado |
| simulator/mcp_server.py | 1040 | Entrada de O2 e saída dos novos balanços |
| simulator/tests/test_extension_conservation.py | 18 | Regressões de matriz, N e batelada |
| simulator/tests/test_asm_acceptor_conservation.py | 23 | Regressões ASM e MCP |
| simulator/tests/test_extensions.py | 1414 | Expectativa antiga de dissolução atualizada |

Os arquivos de extensão e interface da tabela estão em `simulator/full_model`.
Não foram executados add, commit, push, checkout ou stash. O symlink `.venv`
não foi incluído em nenhuma operação de Git.
