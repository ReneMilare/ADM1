#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/_common.sh"
if (($#)); then
    printf 'Opcao desconhecida: %s\n' "$1" >&2
    exit 1
fi
project_root=$ADM1_PROJECT_ROOT
venv_python=$(get_venv_python_path "$project_root")
write_section "Estado local do ambiente"
write_note "Projeto: $project_root"
if [[ -f $venv_python ]]; then
    py_version=$("$venv_python" -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    printf 'Python (.venv): %s\n' "$py_version"
    "$venv_python" -c "import importlib.util; mods=['streamlit','numpy','pandas','plotly','pydantic','scipy']; print('\n'.join(f'{name}=' + ('ok' if importlib.util.find_spec(name) else 'missing') for name in mods))"
else
    printf 'AVISO: Ambiente virtual nao encontrado. Rode ./scripts/setup_local.sh primeiro.\n' >&2
fi
write_section "Leitura rapida"
printf '%s\n' '- O app principal roda sem RAG interno.' '- Os fluxos de simulacao, comparacao, design e validacao continuam locais.' '- Para abrir a interface: ./scripts/run_webapp.sh'
