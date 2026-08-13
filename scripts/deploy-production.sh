#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/.." && pwd)

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI was not found. Install Docker Engine and the Compose plugin first." >&2
    exit 1
fi
if [[ ! -f "${repo_root}/.env.production" ]]; then
    echo "Missing .env.production. Run bash ./scripts/init-production.sh first." >&2
    exit 1
fi

cd "${repo_root}"
compose=(docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml)

get_value() {
    sed -n "s/^${1}=//p" .env.production | head -n 1
}

API_PUBLIC_DOMAIN=$(get_value "API_PUBLIC_DOMAIN")
ADMIN_PUBLIC_DOMAIN=$(get_value "ADMIN_PUBLIC_DOMAIN")
ADMIN_API_TOKEN=$(get_value "ADMIN_API_TOKEN")

docker info >/dev/null
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait --wait-timeout 180
"${compose[@]}" exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head

curl --fail --silent --show-error --max-time 15 --retry 10 --retry-all-errors --retry-delay 2 \
    "https://${API_PUBLIC_DOMAIN}/health" >/dev/null
status=$(curl --fail --silent --show-error --max-time 15 --retry 3 --retry-all-errors --retry-delay 2 \
    -H "Authorization: Bearer ${ADMIN_API_TOKEN}" \
    "https://${API_PUBLIC_DOMAIN}/api/v1/operations/status")
printf '%s\n' "${status}"

if ! grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' <<<"${status}"; then
    echo "Production operational status requires action; inspect the JSON above." >&2
    exit 1
fi

echo "Deployment completed."
echo "API health: https://${API_PUBLIC_DOMAIN}/health"
echo "Admin web:  https://${ADMIN_PUBLIC_DOMAIN}"
