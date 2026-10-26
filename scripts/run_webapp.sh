#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$script_dir/_common.sh"
port=8501
headless=false
while (($#)); do
    case $1 in
        --port) [[ $# -ge 2 ]] || { printf 'Valor ausente para --port\n' >&2; exit 1; }; port=$2; shift 2 ;;
        --port=*) port=${1#*=}; shift ;;
        --headless) headless=true; shift ;;
        *) printf 'Opcao desconhecida: %s\n' "$1" >&2; exit 1 ;;
    esac
done
[[ $port =~ ^[0-9]+$ ]] || { printf 'Porta invalida: %s\n' "$port" >&2; exit 1; }
project_root=$ADM1_PROJECT_ROOT
venv_python=$(get_venv_python_path "$project_root")
if [[ ! -f $venv_python ]]; then
    printf 'Ambiente virtual nao encontrado. Rode ./scripts/setup_local.sh primeiro.\n' >&2
    exit 1
fi
write_section "Subindo webapp local"
write_note "Projeto: $project_root"
write_note "Porta: $port"
streamlit_args=(-m streamlit run "$project_root/webapp/app.py" --server.port "$port")
if [[ $headless == true ]]; then
    streamlit_args+=(--server.headless true)
fi
cd -- "$project_root"
"$venv_python" "${streamlit_args[@]}"
