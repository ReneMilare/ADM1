"""WebApp ADM1.

Estrutura de camadas (do mais puro ao mais acoplado a Streamlit):

    webapp/
    ├── contracts.py         — contratos canônicos (sem Streamlit)
    ├── features/            — actions por feature (sem Streamlit)
    ├── state/               — adaptadores e resolvers (sem Streamlit)
    ├── services/            — serviços de infraestrutura
    ├── components/          — componentes visuais Streamlit
    ├── pages/               — orquestradores de página (finos)
    │   └── sections/        — seções coesas de cada página
    └── utils/               — utilitários
"""
