#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/.." && pwd)

if [[ "${1:-}" != "--confirm-test-reset" || $# -ne 1 ]]; then
    echo "This permanently removes this local Compose project's PostgreSQL, Redis, and MinIO data." >&2
    echo "Re-run with: bash ./scripts/reset-test-environment.sh --confirm-test-reset" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI was not found. Install Docker Engine and the Compose plugin first." >&2
    exit 1
fi

if [[ ! -f "${repo_root}/.env" ]]; then
    echo "The .env file is missing. This reset script is only for the local Docker test environment." >&2
    exit 1
fi

cd "${repo_root}"

if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running or the current user cannot access it." >&2
    exit 1
fi

echo "WARNING: Removing local test data: PostgreSQL, Redis, and MinIO volumes." >&2
docker compose down --volumes --remove-orphans

echo "Recreating local test services..."
docker compose up -d --wait --wait-timeout 120

echo "Applying database migrations..."
docker compose exec -T api python -m alembic -c /app/apps/api/alembic.ini upgrade head

echo "Test environment reset completed."
