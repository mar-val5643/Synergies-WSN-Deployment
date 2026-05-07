#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGE_AGENT_ENV_FILE="${REPO_ROOT}/edge_agent/.env"
EXPORTER_ENV_FILE="${REPO_ROOT}/openhab_exporter/.env"
CONFIG_ENV_FILE="${REPO_ROOT}/config.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"

echo "=== Synergies WSN: Edge Features Deployment ==="

# Load core config to get defaults
if [[ ! -f "${CONFIG_ENV_FILE}" ]]; then
  echo "Error: config.env not found at ${CONFIG_ENV_FILE}."
  exit 1
fi
source "${CONFIG_ENV_FILE}"

# 2. Validation
if [[ -z "${SITE_ID:-}" ]]; then
  echo "Error: SITE_ID not found in config.env"
  exit 1
fi

# Determine OpenHAB base URL - use from config.env or construct from hostname/port
OPENHAB_HTTP_PORT="${OPENHAB_HTTP_PORT:-8080}"
OH_BASE_URL="http://${WSN_HOSTNAME:-openhab}:${OPENHAB_HTTP_PORT}"

echo "Writing environment files for SITE_ID: ${SITE_ID}"

cat > "${EDGE_AGENT_ENV_FILE}" <<EOF
SITE_ID=${SITE_ID}
OH_BASE_URL=${OH_BASE_URL}
OH_TOKEN=${OH_TOKEN}
MQTT_HOST=${MQTT_HOST}
MQTT_PORT=${MQTT_PORT}
MQTT_TLS=${MQTT_TLS}
MQTT_USERNAME=${MQTT_USERNAME}
MQTT_PASSWORD=${MQTT_PASSWORD}
MQTT_CA=${MQTT_CA}
MQTT_CERT=${MQTT_CERT}
MQTT_KEY=${MQTT_KEY}
TELEMETRY_INTERVAL_SEC=60
HEARTBEAT_INTERVAL_SEC=30
CACHE_TTL_SEC=300
CACHE_SIZE=1000
EOF

echo "Edge agent environment file created."

cat > "${EXPORTER_ENV_FILE}" <<EOF
SITE_ID=${SITE_ID}
OH_BASE_URL=${OH_BASE_URL}
OH_TOKEN=${OH_TOKEN}
MQTT_HOST=${MQTT_HOST}
MQTT_PORT=${MQTT_PORT}
EXPORTER_INTERVAL_SECONDS=${EXPORTER_INTERVAL_SECONDS:-300}
OPENHAB_PERSISTENCE_SERVICE=${OPENHAB_PERSISTENCE_SERVICE:-influxdb}
EOF

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Error: Docker compose file not found at ${COMPOSE_FILE}."
  exit 1
fi

COMPOSE_BIN="docker compose"
if ! command -v docker compose >/dev/null 2>&1; then
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_BIN="docker-compose"
    else
        # Fallback to the venv location used in your core deploy script
        COMPOSE_BIN="${REPO_ROOT}/pythonvenv/bin/docker-compose"
    fi
fi

echo "Starting edge-agent using docker-compose.yml with edge profile..."

# Try to find docker-compose in common locations or PATH
if [[ -n "${SITE_ID}" ]]; then
    echo "Deploying edge-agent..."
    $COMPOSE_BIN -f "${COMPOSE_FILE}" --env-file "${CONFIG_ENV_FILE}" --profile edge up -d --no-deps edge-agent

    echo "Deploying openhab-exporter..."
    $COMPOSE_BIN -f "${COMPOSE_FILE}" --env-file "${CONFIG_ENV_FILE}" --profile edge up -d --no-deps openhab-exporter
else
    echo "Error: SITE_ID is empty. Deployment aborted."
    exit 1
fi
echo
echo "Edge features deployment completed."
echo "You can check running containers with:"
echo "  docker ps"
