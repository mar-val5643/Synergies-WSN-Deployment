# Edge Agent

The edge agent is a Python service that acts as a bridge between MQTT commands and the openHAB REST API. It enables remote control and monitoring of openHAB instances through MQTT without exposing the automation system to the public internet.

## Overview

The edge agent:
- Subscribes to MQTT command topics to receive requests
- Forwards commands to the local openHAB REST API
- Publishes responses back via MQTT
- Publishes status and telemetry data for monitoring
- Supports response caching for idempotent operations

## Architecture

```
External Controller → MQTT Broker → Edge Agent → openHAB REST API
                                                      ↓
External Controller ← MQTT Broker ← Edge Agent ← openHAB
```

## MQTT Topics

The edge agent uses the following topic pattern (matching the exporter pattern):

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `openhab/{site_id}/command` | Client → Agent | Send commands to openHAB |
| `openhab/{site_id}/response` | Agent → Client | Receive responses from openHAB |
| `openhab/{site_id}/status` | Agent → Client | Heartbeat/status messages |
| `openhab/{site_id}/data` | Agent → Client | Telemetry data |

For site ID "GRC-10", the topics would be:
- `openhab/GRC-10/command`
- `openhab/GRC-10/response`
- `openhab/GRC-10/status`
- `openhab/GRC-10/data`

## Configuration

### Environment Variables

The edge agent is configured via environment variables. Key settings:

**Required:**
- `SITE_ID` - Site identifier (e.g., "GRC-10")
- `MQTT_HOST` - MQTT broker hostname (e.g., "mqtt")
- `MQTT_PORT` - MQTT broker port (default: 8883, use 1883 for non-TLS)

**Optional:**
- `MQTT_TLS` - Use TLS (default: true, set to false for local broker)
- `MQTT_USERNAME` / `MQTT_PASSWORD` - MQTT authentication
- `MQTT_COMMAND_TOPIC` - Override default command topic
- `MQTT_RESPONSE_TOPIC` - Override default response topic
- `MQTT_STATUS_TOPIC` - Override default status topic
- `MQTT_DATA_TOPIC` - Override default data topic
- `OH_BASE_URL` - openHAB base URL (default: "http://localhost:8080")
- `OH_TOKEN` - openHAB API token for authentication
- `OH_TIMEOUT_SEC` - HTTP timeout in seconds (default: 10)
- `TELEMETRY_INTERVAL_SEC` - Telemetry publish interval (default: 60)
- `HEARTBEAT_INTERVAL_SEC` - Heartbeat interval (default: 30)
- `CACHE_TTL_SEC` - Response cache TTL (default: 300)
- `CACHE_SIZE` - Maximum cache size (default: 1000)

### Configuration File

A YAML configuration file is available at `configs/edge_agent_config.yaml` for reference, though the edge agent currently reads from environment variables only.

## Deployment

The edge agent is deployed as a Docker container via `docker-compose.yml`.

### Deploy

```bash
# From the repository root
docker-compose --env-file config.env up -d edge-agent
```

### Check Status

```bash
# Check if container is running
docker ps | grep edge-agent

# View logs
docker logs edge-agent

# Follow logs
docker logs -f edge-agent
```

### Restart

```bash
docker-compose --env-file config.env restart edge-agent
```

## Command Format

Commands sent to the edge agent via MQTT should follow this JSON format:

```json
{
  "method": "GET",
  "endpoint": "/rest/items/MyItem/state",
  "data": null,
  "correlation_id": "unique-uuid-here",
  "idempotency_key": "optional-key-for-caching"
}
```

### Field Descriptions

- **`method`**: HTTP method (`GET`, `POST`, `PUT`, `DELETE`)
- **`endpoint`**: openHAB REST API endpoint (e.g., `/rest/items`, `/rest/items/MyItem/state`)
- **`data`**: Request body (for POST/PUT) - can be a string, number, or JSON object
- **`correlation_id`**: Unique identifier to match request with response
- **`idempotency_key`**: (Optional) Key for response caching - same key returns cached response

### Response Format

```json
{
  "correlation_id": "unique-uuid-here",
  "status_code": 200,
  "timestamp": "2026-02-15T08:55:41.691318+00:00",
  "latency_ms": 42.84,
  "data": "..."
}
```

## Test Script

A test script (`test_agent.py`) is provided to interact with the edge agent.

### Prerequisites

The test script requires `paho-mqtt`. It's available in the project's virtual environment:

```bash
source pythonvenv/bin/activate
```

### Usage

#### Get All Things

Retrieve all things from openHAB:

```bash
python edge_agent/test_agent.py \
  --host localhost \
  --port 1883 \
  --site-id-file ./data/site/ID \
  get-things
```

#### Get Last Value of an Item

Get the last persisted value for a specific item:

```bash
python edge_agent/test_agent.py \
  --host localhost \
  --port 1883 \
  --site-id-file ./data/site/ID \
  get-last-value \
  --item ShellyPlus_PM_Mini_Power_Consumption
```

### Command Line Options

```
--host HOST              MQTT broker host (default: localhost)
--port PORT              MQTT broker port (default: 1883)
--username USERNAME       MQTT username (optional)
--password PASSWORD       MQTT password (optional)
--tls                     Use TLS (default: false)
--site-id SITE_ID         Site ID (overrides file and env var)
--site-id-file FILE       Path to file containing site ID
--topic-prefix PREFIX     Topic prefix (default: openhab)
--timeout SECONDS         Response timeout (default: 10)
-v, --verbose             Enable verbose logging
```

## Common Use Cases

### Get All Items

```bash
python edge_agent/test_agent.py \
  --host localhost --port 1883 \
  --site-id-file ./data/site/ID \
  get-things
```

### Get Item State

Use the `publish_command.py` example:

```bash
python edge_agent/examples/publish_command.py \
  --host localhost \
  --port 1883 \
  --command-topic openhab/GRC-10/command \
  --response-topic openhab/GRC-10/response \
  --endpoint "/rest/items/MyItem/state" \
  --method GET \
  --tls false
```

### Set Item State

```bash
python edge_agent/examples/publish_command.py \
  --host localhost \
  --port 1883 \
  --command-topic openhab/GRC-10/command \
  --response-topic openhab/GRC-10/response \
  --endpoint "/rest/items/MyItem/state" \
  --method POST \
  --data "ON" \
  --tls false
```

## Troubleshooting

### Edge Agent Not Responding

1. Check if container is running:
   ```bash
   docker ps | grep edge-agent
   ```

2. Check logs:
   ```bash
   docker logs edge-agent
   ```

3. Verify MQTT connection:
   - Look for "MQTT connected" in logs
   - Check `MQTT_HOST` and `MQTT_PORT` in environment

4. Verify openHAB connection:
   - Check `OH_BASE_URL` in environment
   - Verify `OH_TOKEN` is set if authentication is required
   - Test openHAB REST API directly

### Authentication Errors

If you see 401 errors:
- Ensure `OH_TOKEN` is set in `config.env`
- Restart the edge agent container after updating config
- Verify the token is valid in openHAB

### MQTT Connection Issues

- Verify MQTT broker is running: `docker ps | grep mqtt-broker`
- Check network connectivity between edge-agent and mqtt-broker
- Verify topic subscriptions in logs

## Files

- `edge_agent.py` - Main edge agent application
- `config.py` - Configuration management
- `mqtt_client.py` - MQTT client implementation
- `openhab_proxy.py` - openHAB REST API client
- `idempotency_cache.py` - Response caching
- `test_agent.py` - Test script for interacting with agent
- `Dockerfile` - Container build definition
- `requirements.txt` - Python dependencies

## Examples

See the `examples/` directory for additional usage examples:
- `publish_command.py` - Publish commands and await responses
- `subscribe_status.py` - Subscribe to status updates

## Related Documentation

- [Edge Agent Overview](docs/overview.md)
- [How to Interact with Edge Agent](docs/how-to-interact.md)
- [MQTT Topics](docs/mqtt-topics.md)
- [Runbook](docs/runbook.md)

