#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/.." && pwd)

get_published_port() {
    local service=$1
    local container_port=$2
    local bindings
    local binding

    if ! bindings=$(docker compose port "${service}" "${container_port}"); then
        echo "Cannot resolve the published port for ${service}:${container_port}." >&2
        return 1
    fi
    binding=${bindings%%$'\n'*}
    if [[ -z "${binding}" ]]; then
        echo "No published port was found for ${service}:${container_port}." >&2
        return 1
    fi
    if [[ ! "${binding}" =~ :([0-9]+)$ ]]; then
        echo "Unexpected published port value for ${service}: ${binding}" >&2
        return 1
    fi

    printf '%s\n' "${BASH_REMATCH[1]}"
}

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI was not found. Install Docker first." >&2
    exit 1
fi

if [[ ! -f "${repo_root}/.env" ]]; then
    echo "The .env file is missing. Copy .env.example to .env and configure local secrets first." >&2
    exit 1
fi

cd "${repo_root}"

if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running or the current user cannot access it." >&2
    exit 1
fi

echo "Starting backend services..."
docker compose up -d --wait --wait-timeout 120

echo "Applying database migrations..."
docker compose exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head

api_port=$(get_published_port "api" 8000)
admin_port=$(get_published_port "admin-web" 80)

echo "Backend started successfully."
echo "API health: http://localhost:${api_port}/health"
echo "Admin web:  http://localhost:${admin_port}"
