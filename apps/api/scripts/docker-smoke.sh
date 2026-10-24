#!/usr/bin/env bash
# Build the API image, start it next to a throwaway Postgres, and check that migrations
# ran and the health endpoints answer. Used by `make api-docker-smoke` and CI.
set -euo pipefail

IMAGE=${IMAGE:-docflow-api:smoke}
NET=docflow-smoke-$$
DB=docflow-smoke-db-$$
API=docflow-smoke-api-$$
PORT=${SMOKE_PORT:-18080}

cleanup() {
  docker rm -f "$API" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build -f apps/api/Dockerfile -t "$IMAGE" .

docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=docflow \
  --health-cmd "pg_isready -U postgres -d docflow" --health-interval 1s --health-retries 30 \
  pgvector/pgvector:pg17 >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$DB")" = healthy ]; do sleep 1; done

docker run -d --name "$API" --network "$NET" -p "$PORT:10000" \
  -e DATABASE_URL="postgresql://postgres:postgres@$DB:5432/docflow" \
  -e ENVIRONMENT=production "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "http://localhost:$PORT/healthz" >/dev/null 2>&1 && break
  sleep 1
done

echo "healthz: $(curl -fsS "http://localhost:$PORT/healthz")"
echo "readyz:  $(curl -fsS "http://localhost:$PORT/readyz")"
echo "migrations: $(docker exec "$DB" psql -U postgres -d docflow -tAc 'SELECT version_num FROM docflow.alembic_version')"
echo "image size: $(docker image inspect "$IMAGE" -f '{{.Size}}' | awk '{printf "%.0f MB", $1/1000/1000}')"
sleep 3
echo "idle memory: $(docker stats --no-stream --format '{{.MemUsage}}' "$API")"
