#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=_common.sh
source "$script_dir/_common.sh"
project_root=$ADM1_PROJECT_ROOT
output_dir=dist
bundle_name=

while (($#)); do
    case "$1" in
        --output-dir) [[ $# -ge 2 ]] || { printf 'Valor ausente para %s\n' "$1" >&2; exit 1; }; output_dir=$2; shift 2 ;;
        --output-dir=*) output_dir=${1#*=}; shift ;;
        --bundle-name) [[ $# -ge 2 ]] || { printf 'Valor ausente para %s\n' "$1" >&2; exit 1; }; bundle_name=$2; shift 2 ;;
        --bundle-name=*) bundle_name=${1#*=}; shift ;;
        *) printf 'Opcao desconhecida: %s\n' "$1" >&2; exit 1 ;;
    esac
done

if [[ -z "${bundle_name//[[:space:]]/}" ]]; then
    bundle_name="ADM1-local-test-$(date +%Y%m%d-%H%M%S)"
fi
case "$output_dir" in
    /*) output_root=$output_dir ;;
    *) output_root="$project_root/$output_dir" ;;
esac
staging_root="$output_root/$bundle_name-staging"
mkdir -p -- "$output_root"
output_root=$(CDPATH='' cd -- "$output_root" && pwd)
staging_root="$output_root/$bundle_name-staging"
if command -v zip >/dev/null 2>&1; then
    archive_path="$output_root/$bundle_name.zip"
    archive_format=zip
else
    archive_path="$output_root/$bundle_name.tar.gz"
    archive_format=tar.gz
fi
rm -rf -- "$staging_root"
rm -f -- "$archive_path"
mkdir -p -- "$staging_root"

should_exclude() {
    local path=$1 name=${1##*/}
    case "$name" in
        dynamic_out.csv|adm1-theme-probe.png|*.pyc|*.pyo|*.pyd) return 0 ;;
    esac
    case "/$path/" in
        */.claude/*|*/.venv/*|*/.git/*|*/pytest-cache-files-*/*|*/root-probe-*/*|*/__pycache__/*|*/.pytest_cache/*|*/.pytype/*) return 0 ;;
    esac
    case "$path/" in
        webapp/user_data/*|simulator/tests/.tmp/*|simulator/tests/tmp_literature_validation/*|simulator/.pyadm1_runtime/probe-*/*|simulator/.pyadm1_runtime/run-*/*|simulator/.pyadm1_runtime/run_*/*|documentation/*|vaultObsidian/*|vaultObsidianADM1/*|dist/*) return 0 ;;
    esac
    return 1
}

copy_file() {
    local source_path=$1 relative_path=${1#"$project_root"/} destination
    if should_exclude "$relative_path"; then return; fi
    destination="$staging_root/$relative_path"
    mkdir -p -- "$(dirname -- "$destination")"
    cp -f -- "$source_path" "$destination"
}

for item in .streamlit scripts simulator vendor webapp .gitignore pyproject.toml pytest.ini README.md requirements.txt; do
    source_path="$project_root/$item"
    if [[ -d "$source_path" ]]; then
        while IFS= read -r -d '' file; do
            copy_file "$file"
        done < <(find "$source_path" -type f -print0)
    elif [[ -f "$source_path" ]]; then
        copy_file "$source_path"
    fi
done

if [[ $archive_format == zip ]]; then
    (cd "$staging_root" && zip -qr "$archive_path" .)
else
    tar -czf "$archive_path" -C "$staging_root" .
fi
size_bytes=$(wc -c < "$archive_path")
size_mb=$(awk -v bytes="$size_bytes" 'BEGIN { printf "%.2f", bytes / 1048576 }')
printf 'BundleName: %s\nFormato: %s\nArquivo: %s\nSizeMB: %s\n' "$bundle_name" "$archive_format" "$archive_path" "$size_mb"
