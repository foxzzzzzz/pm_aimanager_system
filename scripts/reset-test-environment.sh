#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/.." && pwd)
utility_image=${UTILITY_IMAGE:-alpine:3.22}

case "${1:-}" in
    --confirm-test-reset)
        if [[ $# -ne 1 ]]; then
            echo "Usage: bash ./scripts/reset-test-environment.sh --confirm-test-reset" >&2
            exit 1
        fi
        environment_name="local test"
        compose=(docker compose)
        environment_file="${repo_root}/.env"
        remove_volumes=true
        ;;
    --confirm-production-data-reset)
        if [[ $# -ne 1 ]]; then
            echo "Usage: bash ./scripts/reset-test-environment.sh --confirm-production-data-reset" >&2
            exit 1
        fi
        environment_name="production Compose acceptance-data"
        compose=(docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml)
        environment_file="${repo_root}/.env.production"
        remove_volumes=false
        ;;
    *)
        echo "This permanently removes project data from PostgreSQL, Redis, and MinIO." >&2
        echo "Local Compose:      bash ./scripts/reset-test-environment.sh --confirm-test-reset" >&2
        echo "Production Compose: bash ./scripts/reset-test-environment.sh --confirm-production-data-reset" >&2
        exit 1
        ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI was not found. Install Docker Engine and the Compose plugin first." >&2
    exit 1
fi

if [[ ! -f "${environment_file}" ]]; then
    echo "The required environment file is missing: ${environment_file}" >&2
    exit 1
fi

cd "${repo_root}"

if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running or the current user cannot access it." >&2
    exit 1
fi

if [[ "${remove_volumes}" == true ]]; then
    echo "WARNING: Removing local test data volumes: PostgreSQL, Redis, and MinIO." >&2
    "${compose[@]}" down --volumes --remove-orphans
    echo "Recreating local test services..."
    "${compose[@]}" up -d --wait --wait-timeout 120
else
    minio_id=$("${compose[@]}" ps -q minio)
    if [[ -z "${minio_id}" ]]; then
        echo "MinIO container is not running; cannot safely resolve its data volume." >&2
        exit 1
    fi
    minio_volume=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${minio_id}")
    if [[ -z "${minio_volume}" ]]; then
        echo "MinIO data volume could not be resolved." >&2
        exit 1
    fi

    echo "WARNING: Resetting ${environment_name} data while preserving Caddy certificates and configuration." >&2
    "${compose[@]}" stop api notification-worker notification-beat minio
    "${compose[@]}" exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
    "${compose[@]}" exec -T redis redis-cli FLUSHALL
    docker run --rm --mount "type=volume,src=${minio_volume},dst=/data" "${utility_image}" sh -c 'find /data -mindepth 1 -delete'
    "${compose[@]}" up -d minio api notification-worker notification-beat
fi

echo "Applying database migrations..."
"${compose[@]}" exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head

echo "Test environment reset completed."
