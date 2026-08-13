#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/.." && pwd)
env_path="${repo_root}/.env.production"
example_path="${repo_root}/.env.production.example"

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required to generate production secrets." >&2
    exit 1
fi

if [[ ! -f "${env_path}" ]]; then
    cp "${example_path}" "${env_path}"
    echo "Created ${env_path}."
else
    echo "Updating ${env_path}; existing values are kept when you submit an empty response."
fi

get_value() {
    local key=$1
    sed -n "s/^${key}=//p" "${env_path}" | head -n 1
}

set_value() {
    local key=$1
    local value=$2
    local temporary_path="${env_path}.tmp"
    awk -v key="${key}" -v value="${value}" '
        BEGIN { replaced = 0 }
        index($0, key "=") == 1 { print key "=" value; replaced = 1; next }
        { print }
        END { if (!replaced) print key "=" value }
    ' "${env_path}" > "${temporary_path}"
    mv "${temporary_path}" "${env_path}"
}

prompt_value() {
    local key=$1
    local label=$2
    local secret=${3:-false}
    local current
    local input
    current=$(get_value "${key}")
    if [[ "${current}" == replace-with-* ]]; then
        current=""
    fi
    if [[ "${secret}" == "true" ]]; then
        read -r -s -p "${label}${current:+ (press Enter to keep existing)}: " input
        echo
    else
        read -r -p "${label}${current:+ [${current}]}: " input
    fi
    if [[ -n "${input}" ]]; then
        set_value "${key}" "${input}"
    elif [[ -z "${current}" ]]; then
        echo "${key} is required." >&2
        exit 1
    fi
}

generate_secret_if_missing() {
    local key=$1
    local current
    current=$(get_value "${key}")
    if [[ -z "${current}" || "${current}" == replace-with-* ]]; then
        set_value "${key}" "$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
        echo "Generated ${key}."
    fi
}

generate_secret_if_missing "POSTGRES_PASSWORD"
generate_secret_if_missing "MINIO_ROOT_PASSWORD"
prompt_value "API_PUBLIC_DOMAIN" "API public domain"
prompt_value "ADMIN_PUBLIC_DOMAIN" "Admin public domain"
prompt_value "TLS_EMAIL" "TLS certificate notification email"
prompt_value "WECHAT_APP_ID" "WeChat Mini Program AppID"
prompt_value "WECHAT_APP_SECRET" "WeChat Mini Program AppSecret" true
prompt_value "WECHAT_SUBSCRIPTION_TEMPLATE_ID" "WeChat subscription template ID"
prompt_value "TENCENT_SECRET_ID" "Tencent Cloud SMS SecretId"
prompt_value "TENCENT_SECRET_KEY" "Tencent Cloud SMS SecretKey" true
prompt_value "TENCENT_SMS_SDK_APP_ID" "Tencent Cloud SMS SDK AppID"
prompt_value "TENCENT_SMS_SIGN_NAME" "Approved Tencent SMS sign name"
prompt_value "TENCENT_SMS_CRITICAL_TEMPLATE_ID" "Approved critical-alert SMS template ID"

set_value "ADMIN_WEB_API_BASE_URL" "https://$(get_value API_PUBLIC_DOMAIN)/api/v1"
set_value "PROJECT_MANAGER_CORS_ORIGINS" "https://$(get_value ADMIN_PUBLIC_DOMAIN)"
set_value "PROJECT_MANAGER_ALLOW_DEV_WECHAT_LOGIN" "false"
generate_secret_if_missing "ADMIN_API_TOKEN"
generate_secret_if_missing "PHONE_HMAC_KEY"
generate_secret_if_missing "PHONE_ENCRYPTION_KEY"

read -r -p "Enable real Tencent SMS delivery now? [y/N]: " enable_sms
if [[ "${enable_sms}" =~ ^[Yy]$ ]]; then
    set_value "PROJECT_MANAGER_SMS_ENABLED" "true"
else
    set_value "PROJECT_MANAGER_SMS_ENABLED" "false"
fi

chmod 600 "${env_path}"
echo "Production configuration is ready at ${env_path}."
