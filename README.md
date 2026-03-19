# Projeto ADM1

Base local para estudo, busca semantica e simulacao ADM1 voltada ao design de reatores de biogas.

## Estado Atual

- Fase 1 concluida: extracao estruturada de PDFs, indice vetorial persistente, embeddings locais via Ollama e MCP de RAG read-only
- Fase 2 concluida: motor ADM1 com backend padrao `pyadm1`, fallback explicito para `reduced` em reatores ainda nao suportados pelo original, persistencia de cenarios e MCP do simulador
- Fase 3 implementada na camada local: validacao automatizada, pipeline de design e ferramentas MCP adicionais; OpenModelica ainda depende da toolchain externa
- Fases W1 a W7 concluidas: shell da interface web em `Streamlit`, simulacao, comparacao de cenarios, design assistido, validacao tecnica, consulta ao acervo RAG e camada de operacao recorrente com presets do usuario, historico, favoritos e configuracoes persistentes

## Estrutura Principal

- `rag/`: extracao, indexacao, busca hibrida e MCP de documentos
- `simulator/`: motor numerico, modelos de reator, benchmark de backends, validacao Fase 3, pipeline de design, persistencia e MCP de simulacao
- `vaultObsidian/`: mapa conceitual, notas tecnicas e plano do projeto
- `webapp/`: interface web local em `Streamlit`

## Como usar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python rag/extract_pdfs.py
python rag/index_documents.py
python rag/mcp_server.py
python simulator/mcp_server.py
python -m simulator.benchmark
python -m simulator.validation
python -m simulator.design_pipeline --substrate "Lodo de Esgoto" --goal balanced --backend auto
streamlit run webapp/app.py
```

## Variaveis de ambiente

- `ADM1_OLLAMA_HOST`: host HTTP do Ollama. Padrao: `http://127.0.0.1:11434`
- `ADM1_EMBED_MODEL`: modelo de embedding. Padrao: `nomic-embed-text`
- `ADM1_CHROMA_COLLECTION`: nome da colecao Chroma. Padrao: `adm1_docs`
- `ADM1_CHUNK_TOKENS`: tamanho alvo dos chunks. Padrao: `450`
- `ADM1_CHUNK_OVERLAP`: overlap fracionario entre janelas. Padrao: `0.2`

## Fluxo Atual

1. PDFs em `documentation/`
2. JSONs estruturados em `rag/extracted/`
3. Banco vetorial persistente em `rag/db/`
4. Simulacoes e cenarios persistidos em `simulator/runs/`
5. Ferramentas MCP para documentos e para o simulador ADM1
6. Benchmark local entre `reduced` e `pyadm1` em `simulator/benchmarks/`
7. Relatorios de validacao da Fase 3 em `simulator/validation_runs/`
8. Pipeline de design de reatores em `simulator/design_pipeline.py`
9. Interface web local em `webapp/app.py`

## Fluxo Recomendado Para Testes Locais

Para distribuir a solucao para outras pessoas testarem localmente, preserve a estrutura completa do projeto e use os scripts em `scripts/`.

### Setup inicial

```powershell
.\scripts\setup_local.ps1
```

O setup prepara o `.venv`, instala as dependencias Python e pergunta se o usuario quer habilitar o RAG agora.

### Verificacao rapida do ambiente

```powershell
.\scripts\check_env.ps1
```

### Subir a interface

```powershell
.\scripts\run_webapp.ps1
```

### Sobre o RAG opcional

- O projeto principal roda sem RAG.
- Sem RAG, os fluxos de simulacao, comparacao, design e validacao continuam funcionais.
- A tela `Consulta Tecnica` passa a depender de indice local em `rag/db`, Ollama local e modelo de embedding `nomic-embed-text`.
- O setup tenta detectar `Ollama` e o modelo; se nao encontrar, pergunta se o usuario quer instalar/baixar.

## Clonando do GitHub

Se voce clonar a partir do repositório Git, inicialize tambem o submodulo vendorizado do PyADM1:

```bash
git clone --recurse-submodules <repo-url>
```

Se o clone ja tiver sido feito sem submodulos:

```bash
git submodule update --init --recursive
```
