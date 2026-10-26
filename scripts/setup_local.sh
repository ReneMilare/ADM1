#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=_common.sh
source "$script_dir/_common.sh"

python_exe=python
while (($#)); do
    case $1 in
        --python-exe)
            if (($# < 2)); then printf '%s\n' 'Falta valor para --python-exe.' >&2; exit 2; fi
            python_exe=$2; shift 2 ;;
        --python-exe=*) python_exe=${1#*=}; shift ;;
        --auto-approve|--yes) shift ;;
        *) printf 'Opcao desconhecida: %s\n' "$1" >&2; exit 2 ;;
    esac
done

project_root=$ADM1_PROJECT_ROOT
requirements_path="$project_root/requirements.txt"
venv_python=$(get_venv_python_path "$project_root")

write_section 'Preparando ambiente Python'
resolve_python_launcher "$python_exe"
python_version=$(get_python_version_string)
if ! test_python_version_compatible "$python_version"; then
    printf 'Python %s encontrado, mas o projeto exige Python 3.11+.\n' "$python_version" >&2
    exit 1
fi
write_note "Python detectado: $python_version"

if [[ ! -f $venv_python ]]; then
    write_section 'Criando ambiente virtual'
    (cd -- "$project_root" && "${PYTHON_LAUNCHER[@]}" -m venv .venv)
else
    write_note 'Ambiente virtual ja existe em .venv'
fi

write_section 'Baixando submodulo vendor/PyADM1'
if command -v git >/dev/null 2>&1 && [[ -e $project_root/.git ]]; then
    git -C "$project_root" submodule update --init --recursive
else
    write_note 'git indisponivel ou fora de um clone; confira se vendor/PyADM1 esta preenchido.'
fi

write_section 'Instalando dependencias Python'
# Venvs criados por ferramentas como uv podem vir sem pip.
"$venv_python" -m pip --version >/dev/null 2>&1 || "$venv_python" -m ensurepip --upgrade
"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -r "$requirements_path"

write_section 'Resumo do app principal'
write_note 'A webapp principal nao inclui mais o RAG interno.'
write_note 'Os fluxos de simulacao, comparacao, design e validacao continuam disponiveis localmente.'
write_note 'Integracoes documentais futuras ficam fora do runtime principal do ADM1.'

write_section 'Concluido'
printf '%s\n' 'Proximo passo: ./scripts/run_webapp.sh'
