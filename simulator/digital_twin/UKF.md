# Fase 2 — estimação de estado e parâmetros

## Uso e contrato temporal

```bash
.venv/bin/python -m simulator.digital_twin.demo --all --estimator ukf --identifiability
```

Sem `--estimator`, a demo continua em malha aberta. O UKF exige janelas diárias
alinhadas. Uma amostra rotulada `d` é a média de `[d,d+1)` e só é assimilada em
`d+1`. AGV, alcalinidade e NH4+-N entram apenas nas linhas finitas do laboratório;
não há interpolação nem repetição do último resultado. A disponibilidade é a
mesma da Fase 1: um dia após o rótulo da amostra. Latências adicionais de
laboratório e amostras fora de ordem ainda não são suportadas pelo UKF.

A coluna de simulação do UKF contém a **previsão antes da assimilação**. A
comparação com malha aberta usa os mesmos dias e sensores. O ponto isolado no
fim da simulação da Fase 1 fica fora da comparação: ele não representa uma média
diária completa. `comparison.json` também compara as previsões com a verdade
sintética sem ruído. O filtro nunca recebe essa verdade.

Saídas adicionais: `twin_ukf_forecast.csv`, `estimated_parameters.csv`,
`comparison.json` e, com a opção correspondente, `identifiability.json`.
`shadow.png` mostra as previsões, a malha aberta e os parâmetros com bandas.

## Identificabilidade antes da filtragem

A análise usa diferenças centrais em log com passo 0,02 para `k_m_ac` e um fator
constante de N afluente, no ponto nominal (8; 1). Cada linha da matriz J é uma sensibilidade de saída
dividida pelo desvio padrão do sensor. Só entram amostras presentes. A matriz de
informação condicional é `JᵀJ`; os desvios abaixo são a raiz da diagonal da sua
inversa, em coordenadas log. São 414 observações por cenário: 360 diárias e 54
semanais, em 120 dias.

| Cenário | Posto | Valores singulares de J | Condição de J | σ log(k) | σ log(fator N) | Correlação |
|---|---:|---|---:|---:|---:|---:|
| steady_noisy | 2 | 72,085; 38,897 | 1,853 | 0,01770 | 0,02324 | 0,498 |
| overload_recovery | 2 | 83,793; 38,577 | 2,172 | 0,01588 | 0,02371 | 0,570 |
| cold_snap_ammonia | 2 | 70,783; 38,720 | 1,828 | 0,01795 | 0,02333 | 0,491 |

Os dois parâmetros são distinguíveis **localmente neste modelo condicional**.
A análise fixa o estado inicial nominal, as outras constantes cinéticas e as
entradas observadas. Não marginaliza incerteza de estado, não demonstra
identificabilidade global e não demonstra que um fator de N diferente a cada
dia seja recuperável. O laboratório semanal limita a reconstrução de pulsos
curtos. O UKF usa um passeio aleatório regularizado para N, cuja banda depende
do ruído de processo escolhido. Os tempos desta análise foram 51,1; 69,1 e
109,8 s, respectivamente, com outras execuções concorrentes.

## Modelo de estimação e decisões

O modelo bioquímico continua sendo o ADM1 completo. O vetor com covariância tem
sete coordenadas: log de `S_ac`, `X_ac`, `S_IN`, `S_IC`, `S_anion`, `k_m_ac` e
fator de N afluente. Acetato e biomassa acetoclástica ligam a cinética ao biogás;
N inorgânico, carbono inorgânico e ânions ligam NH4+-N, pH e alcalinidade.
Os outros estados acompanham a média ponderada das integrações, sem covariância
própria nem correção direta pela inovação. Isso reduz de 63 para 15 integrações
por dia no assembly canônico de 29 estados, incluindo os dois parâmetros.
A incerteza fica subestimada se estados omitidos forem relevantes.

O fator multiplica `S_IN` do afluente nominal. Para aumentos de N, a mesma
quantidade molar é adicionada a `S_anion`, como NH4Cl, seguindo o cenário de
amônia. Na redução de N, o modelo remove ânions até zero e compensa o restante por
um cátion forte equivalente. Assim, a mudança de N não introduz uma mudança
artificial de carga, mesmo quando o afluente nominal tem poucos ânions.
O modelo não distingue sais de amônio de entrada como NH3 livre.

Os parâmetros iniciais são `k_m_ac=8` e fator N=1. O filtro não conhece 5,5 nem o
pulso de fator 4 do cenário. `k_hyd_ch` permanece nominal. A função
`make_default_ukf_config` em `simulator/core/defaults.py` centraliza a criação
da configuração Pydantic estrita, com validação em atribuição.

| Coordenada em log | σ inicial | σ processo por √dia |
|---|---:|---:|
| S_ac | 0,60 | 0,150 |
| X_ac | 0,15 | 0,020 |
| S_IN | 0,10 | 0,005 |
| S_IC | 0,10 | 0,010 |
| S_anion | 0,10 | 0,020 |
| k_m_ac | 0,30 | 0,005 |
| fator N | 0,40 | 0,120 |

Esses valores são hipóteses de engenharia, não valores identificados. Acetato
recebe mais liberdade para acomodar composição afluente desconhecida; biomassa
e cinética variam mais devagar; N recebe maior liberdade para seguir mudanças
de alimentação. O ruído diagonal é aplicado no início da janela, antes da
propagação determinística. As mesmas integrações geram o estado no fim e a
média diária de cada sensor. Isso mantém a covariância cruzada com a grandeza
que foi de fato medida, sem substituir a média pelo valor no fim do dia.

O ruído de medição vem de `default_sensor_suite()` e usa exatamente
`σ = noise_rel * abs(previsão) + noise_abs`, como o gerador de medidas. Só os
sensores com amostra finita participam da atualização. Não há rejeição robusta
de outliers nem estimação de deriva dos sensores nesta fase.

A transformação unscented usa α=1, β=2 e κ=0. Os pesos de média são não negativos,
o que preserva concentrações dos estados sem correção direta. Os estados
filtrados são exponenciais. As bandas são `exp(μ ± 2σ_log)`; a coluna principal é
a mediana `exp(μ)` e a coluna `_sigma` é o desvio padrão físico lognormal. A banda
assimétrica preserva positividade. As bandas não são intervalos calibrados de
cobertura experimental. Há reparo espectral mínimo da covariância para erros
de arredondamento e limites de log [-30,20] na decodificação.

Referência do UKF: Julier & Uhlmann (2004),
[Unscented Filtering and Nonlinear Estimation](https://www3.nd.edu/~lemmon/courses/ee67033/pubs/unscented-filter-julier-proceedings-2004.pdf),
doi:10.1109/JPROC.2003.823141. A implementação usa apenas NumPy e as dependências
já presentes no projeto.

## Resultados de referência — 120 dias

Execução de 2026-11-01: cenários padrão, seed de sensores 0, aquecimento de
200 dias, afluente observado, configuração acima e OpenBLAS com uma thread.
Tempos de parede com cenários executados em paralelo. As métricas abaixo usam
previsões antes da assimilação e somente pares de amostras disponíveis: 120
médias de biogás e 18 resultados de cada laboratório. Cada célula mostra MAPE
em %, **malha aberta → UKF**. Os parâmetros são medianas ± desvio padrão físico.

| Cenário | Biogás | AGV | NH4+-N | k_m_ac final [d⁻¹] | Tempo UKF / total [s] |
|---|---:|---:|---:|---:|---:|
| steady_noisy | 14,46 → 7,57 | 54,93 → 63,10 | 5,05 → 6,78 | 5,352 ± 0,195 | 273,7 / 299,7 |
| overload_recovery | 15,85 → 9,42 | 55,75 → 71,50 | 5,43 → 6,96 | 5,274 ± 0,193 | 260,9 / 282,7 |
| cold_snap_ammonia | 16,02 → 8,64 | 59,27 → 60,46 | 9,78 → 8,17 | 5,365 ± 0,194 | 267,9 / 293,9 |

A verdade sintética permite avaliar os mesmos modelos em **todos os 120 dias**,
incluindo os dias sem laboratório. Esses números têm suporte temporal diferente
do quadro anterior e não devem ser comparados diretamente com o MAPE contra
as 18 amostras ruidosas.

| Cenário | Biogás, verdade diária | AGV, verdade diária | NH4+-N, verdade diária |
|---|---:|---:|---:|
| steady_noisy | 14,47 → 6,90 | 59,13 → 34,07 | 2,07 → 4,22 |
| overload_recovery | 15,90 → 8,70 | 59,85 → 39,24 | 2,57 → 4,64 |
| cold_snap_ammonia | 15,98 → 8,14 | 62,75 → 31,61 | 7,79 → 6,78 |

O ganho de biogás aparece nas duas comparações dos três cenários. O AGV melhora
contra a verdade diária, mas piora nos dias de laboratório. O NH4+-N melhora no
caso com pulso e piora nos outros dois. Estimar os parâmetros não garante
melhorar todos os observáveis. A alimentação de DQO é amostrada semanalmente;
seu erro e o padrão semanal não observado podem contaminar as estimativas de
estado e de cinética. Esta é uma hipótese de explicação, não uma causa isolada
por este experimento.

O fator N final foi 1,081 ± 0,325; 1,038 ± 0,313; e 1,035 ± 0,318,
respectivamente. No caso frio, o pico estimado foi **3,183 ± 1,089 no dia 77**.
A verdade foi fator 4 nos dias 65–72. A banda em log no pico foi [1,687; 6,004].
O atraso de resposta e a amplitude reduzida mostram a limitação de reconstruir
um pulso com laboratório semanal e regularização por passeio aleatório.

Um ensaio adicional de partida antecipou o pulso para os dias 10–14 e o frio
para os dias 8–15, com 35 dias totais. Nesse ensaio, o MAPE de biogás contra
sensores foi **11,56 → 13,79%**, e contra a verdade diária **11,05 → 13,35%**.
Portanto, não há garantia de melhora se a perturbação ocorre durante a
calibração inicial. A regressão do caso frio preserva os dias originais dos
eventos e filtra o prefixo de 84 dias do conjunto de medidas original de
120 dias (biogás: 15,02 → 9,90% contra sensores e 15,07 → 9,45% contra a
verdade); as regressões estacionária e de sobrecarga usam
21 dias, com a sobrecarga antecipada para os dias 8–12.

Regenerar o cenário com duração de 84 dias muda a realização do ruído, pois o
gerador de sensores consome vetores aleatórios cujo tamanho depende do horizonte.
Nesse conjunto distinto, o MAPE de biogás foi 13,66 → 16,03%. Isso é outra
evidência de que a melhora não é robusta a toda realização de ruído. A regressão
com prefixo mantém exatamente os dados do cenário de referência e nunca usa
medições futuras para atualizar o filtro.

Os ensaios são sintéticos, com uma seed por cenário. Ainda faltam validação em
dados de planta, análise de cobertura das bandas, teste de outros estados
iniciais e ruídos, marginalização da incerteza dos estados omitidos e tratamento
de latências laboratoriais adicionais. O checkpoint final guarda o estado ADM1;
retomar a distribuição do filtro exigiria salvar também média, covariância e
configuração do UKF.

## Verificação

- `.venv/bin/python -m pytest simulator/tests -q`: **647 passed, 1 deselected,
  1 xfailed**, em **254,14 s**, com `OPENBLAS_NUM_THREADS=1` e cache gravável do
  Matplotlib. Os 14 testes novos passaram. O `xfail` de microalgas e a exclusão
  por marcador `slow` já existiam. Nenhum valor esperado de teste antigo mudou.
- `.venv/bin/python -m simulator.digital_twin.demo --all`: concluída em malha
  aberta; três execuções individuais com `--estimator ukf` concluídas nos casos
  padrão. JSONs, CSVs e gráficos dos três casos foram verificados. A integração
  da análise de identificabilidade também foi exercitada num caso de um dia.
- `git diff --check`: sem erros. A webapp não foi alterada. Não houve operação
  de add, commit, push, checkout ou stash.
