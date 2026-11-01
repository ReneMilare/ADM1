# Correção cinética pela temperatura

A opção `temperature_kinetics="siegrist2002"` aplica ao ADM1 completo os fatores exp(θ(T−35)) da Tabela 3 de Siegrist et al. (2002), DOI 10.1021/es010139p. O padrão `off` preserva o comportamento anterior, inclusive a correção histórica do TPAD. No modo Siegrist, cada fase do TPAD usa sua própria temperatura, sem somar a correção histórica. No reator de duas fases comum, ambas usam a temperatura operacional.

Valores cinéticos configurados e overrides explícitos são referências a 35 °C; os parâmetros de extensões não recebem correção Siegrist por falta de fonte. A desintegração `k_dis` permanece constante, pois o modelo de Siegrist não possui esse processo. Para C4, ausente da tabela, adotam-se θ=0,055 para uptake e decaimento, como oxidação anaeróbia, e θ=0,10 para K_S, como propionato. A constante ADM1 `K_I_nh3` corresponde à inibição acetotrófica; não existe parâmetro independente para propionato.

PyADM1 e reduced não aplicam a opção e registram aviso nos metadados. O modelo não prevê a transição brusca entre populações mesófilas e termófilas em um único tanque.
