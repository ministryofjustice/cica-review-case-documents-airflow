#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"

ROOT_TEMPLATE="${REPO_ROOT}/.env_template"
ROOT_ENV="${REPO_ROOT}/.env"
LOCAL_TEMPLATE="${REPO_ROOT}/local-dev-environment/.env_template"
LOCAL_ENV="${REPO_ROOT}/local-dev-environment/.env"

MISSING_REQUIRED=()

is_wsl() {
    [[ -f /proc/version ]] && grep -qiE "microsoft|wsl" /proc/version
}

print_header() {
    echo ""
    echo "== $1 =="
}

check_command() {
    local command_name="$1"
    local install_hint="$2"
    local required="$3"

    if command -v "${command_name}" >/dev/null 2>&1; then
        echo "[ok] ${command_name}"
        return
    fi

    if [[ "${required}" == "required" ]]; then
        echo "[missing] ${command_name} (required)"
        MISSING_REQUIRED+=("${command_name}: ${install_hint}")
    else
        echo "[missing] ${command_name} (optional)"
        echo "         Install hint: ${install_hint}"
    fi
}

check_python_version() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo "[missing] python3 (required)"
        MISSING_REQUIRED+=("python3: sudo apt update && sudo apt install -y python3 python3-venv")
        return
    fi

    local version
    version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    echo "[ok] python3 ${version}"

    local major minor
    major="${version%%.*}"
    minor="${version##*.}"
    if (( major < 3 || (major == 3 && minor < 12) )); then
        echo "[warning] Python 3.12+ is recommended for this repo"
    fi
}

prompt_yes_no() {
    local prompt="$1"
    local default_yes="$2"
    local reply

    while true; do
        if [[ "${default_yes}" == "yes" ]]; then
            read -rp "${prompt} [Y/n]: " reply
            reply="${reply:-Y}"
        else
            read -rp "${prompt} [y/N]: " reply
            reply="${reply:-N}"
        fi

        case "${reply}" in
            Y|y) return 0 ;;
            N|n) return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

is_secret_key() {
    local key="$1"
    [[ "${key}" =~ (SECRET|TOKEN|PASSWORD|KEY) ]]
}

prompt_env_value() {
    local key="$1"
    local placeholder="$2"
    local current_value="${3:-}"
    local user_value=""

    while [[ -z "${user_value}" ]]; do
        if is_secret_key "${key}"; then
            if [[ -n "${current_value}" ]]; then
                read -rsp "Value for ${key} (${placeholder}) [press Enter to keep current env value]: " user_value
                echo ""
                if [[ -z "${user_value}" ]]; then
                    user_value="${current_value}"
                fi
            else
                read -rsp "Value for ${key} (${placeholder}): " user_value
                echo ""
            fi
        else
            if [[ -n "${current_value}" ]]; then
                read -rp "Value for ${key} (${placeholder}) [${current_value}]: " user_value
                user_value="${user_value:-${current_value}}"
            else
                read -rp "Value for ${key} (${placeholder}): " user_value
            fi
        fi

        if [[ -z "${user_value}" ]]; then
            echo "Value cannot be empty."
        fi
    done

    printf '%s' "${user_value}"
}

create_env_from_template() {
    local template_path="$1"
    local output_path="$2"

    if [[ ! -f "${template_path}" ]]; then
        echo "[skip] Template not found: ${template_path}"
        return
    fi

    if [[ -f "${output_path}" ]]; then
        if ! prompt_yes_no "${output_path} already exists. Overwrite" "no"; then
            echo "[skip] Keeping existing ${output_path}"
            return
        fi
    fi

    local tmp_output
    tmp_output="$(mktemp)"

    while IFS= read -r line || [[ -n "${line}" ]]; do
        if [[ "${line}" =~ ^[[:space:]]*# ]] || [[ -z "${line}" ]]; then
            echo "${line}" >> "${tmp_output}"
            continue
        fi

        if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"

            if [[ "${value}" =~ ^\<[^\>]+\>$ ]]; then
                local placeholder="${value:1:${#value}-2}"
                local default_from_env="${!key-}"
                local resolved_value
                resolved_value="$(prompt_env_value "${key}" "${placeholder}" "${default_from_env}")"
                echo "${key}=${resolved_value}" >> "${tmp_output}"
            else
                echo "${line}" >> "${tmp_output}"
            fi
        else
            echo "${line}" >> "${tmp_output}"
        fi
    done < "${template_path}"

    mv "${tmp_output}" "${output_path}"
    chmod 600 "${output_path}"
    echo "[created] ${output_path}"
}

setup_python_env() {
    if ! command -v uv >/dev/null 2>&1; then
        echo "[skip] uv not installed, cannot auto-create virtual environment"
        return
    fi

    if prompt_yes_no "Create/update project virtualenv with uv venv + uv sync" "yes"; then
        (cd "${REPO_ROOT}" && uv venv && uv sync)
        echo "[done] Python environment ready at ${REPO_ROOT}/.venv"
    else
        echo "[skip] Python environment setup skipped"
    fi
}

main() {
    print_header "WSL Local Setup"

    if is_wsl; then
        echo "Detected WSL environment"
    else
        echo "Warning: WSL was not detected. Script will continue."
    fi

    print_header "Checking Required Tooling"
    check_command "bash" "Usually preinstalled on Ubuntu" "required"
    check_command "curl" "sudo apt update && sudo apt install -y curl" "required"
    check_command "git" "sudo apt update && sudo apt install -y git" "required"
    check_command "docker" "Install Docker Desktop or: sudo apt update && sudo apt install -y docker.io docker-compose-plugin" "required"
    check_command "uv" "curl -LsSf https://astral.sh/uv/install.sh | sh" "required"
    check_python_version

    print_header "Checking Optional Tooling"
    check_command "kubectl" "sudo apt update && sudo apt install -y kubectl" "optional"
    check_command "jq" "sudo apt update && sudo apt install -y jq" "optional"

    if (( ${#MISSING_REQUIRED[@]} > 0 )); then
        print_header "Missing Required Tooling"
        printf '%s\n' "${MISSING_REQUIRED[@]}"
        echo ""
        echo "Install missing tooling, then rerun this script."
        exit 1
    fi

    print_header "Generating .env Files"
    if prompt_yes_no "Create/update root .env from .env_template" "yes"; then
        create_env_from_template "${ROOT_TEMPLATE}" "${ROOT_ENV}"
    else
        echo "[skip] Root .env generation skipped"
    fi

    if prompt_yes_no "Create/update local-dev-environment/.env from its template" "yes"; then
        create_env_from_template "${LOCAL_TEMPLATE}" "${LOCAL_ENV}"
    else
        echo "[skip] local-dev-environment/.env generation skipped"
    fi

    print_header "Python Environment"
    setup_python_env

    print_header "Next Steps"
    echo "1) Start local environment:"
    echo "   cd local-dev-environment && docker compose up -d --force-recreate"
    echo "2) Run ingestion pipeline from repo root:"
    echo "   ./run-ingestion-local.sh"
}

main "$@"