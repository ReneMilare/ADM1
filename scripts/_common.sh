#!/usr/bin/env bash
set -euo pipefail

ADM1_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ADM1_PROJECT_ROOT="$(cd -- "$ADM1_SCRIPT_DIR/.." && pwd -P)"

write_section() { printf '\n==> %s\n' "$1"; }
write_note() { printf ' - %s\n' "$1"; }
get_venv_python_path() { printf '%s/.venv/bin/python\n' "${1:-$ADM1_PROJECT_ROOT}"; }

# Return success for confirmation, failure for rejection.
confirm_action() {
    local prompt=$1 default=${2:-true} auto_approve=${3:-false} response suffix
    if [[ $auto_approve == true ]]; then
        [[ $default == true ]]
        return
    fi
    if [[ $default == true ]]; then suffix='[Y/n]'; else suffix='[y/N]'; fi
    read -r -p "$prompt $suffix " response || response=''
    response=$(printf '%s' "$response" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    case $response in
        y|yes|s|sim) return 0 ;;
        n|no|nao|n?o) return 1 ;;
        *) [[ $default == true ]] ;;
    esac
}

resolve_python_launcher() {
    local preferred=${1:-python}
    if command -v "$preferred" >/dev/null 2>&1; then
        PYTHON_LAUNCHER=("$preferred")
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_LAUNCHER=(python3)
    elif command -v py >/dev/null 2>&1; then
        PYTHON_LAUNCHER=(py -3.11)
    else
        printf '%s\n' 'Python 3.11+ nao foi encontrado no PATH. Instale Python antes de rodar este script.' >&2
        return 1
    fi
}

get_python_version_string() {
    "${PYTHON_LAUNCHER[@]}" -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
}

test_python_version_compatible() {
    local major minor rest
    IFS=. read -r major minor rest <<< "$1"
    [[ $major =~ ^[0-9]+$ && $minor =~ ^[0-9]+$ ]] || return 1
    (( major > 3 || (major == 3 && minor >= 11) ))
}
