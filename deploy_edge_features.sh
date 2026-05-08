#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_ENV_FILE="${REPO_ROOT}/config.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"

echo "=== Synergies WSN: Edge Features Deployment ==="

# Load core config to get defaults
if [[ ! -f "${CONFIG_ENV_FILE}" ]]; then
  echo "Error: config.env not found at ${CONFIG_ENV_FILE}."
  exit 1
fi
source "${CONFIG_ENV_FILE}"

COMPOSE_BIN="/usr/bin/docker-compose"

echo "Deploying Agent and Exporter for Site: ${SITE_ID}..."

$COMPOSE_BIN -f "${COMPOSE_FILE}" --env-file "${CONFIG_ENV_FILE}" --profile edge up -d

echo "Deployment complete."
