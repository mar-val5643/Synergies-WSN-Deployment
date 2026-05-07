# openHAB Exporter

A Python service that periodically collects data from openHAB and publishes it to an MQTT broker.

## Overview

The openHAB Exporter connects to an openHAB instance via REST API, collects the latest state for all items grouped by things/channels, and publishes the data to an MQTT broker using a hierarchical topic structure.

## Features

- **Periodic Data Collection**: Automatically collects data from openHAB at configurable intervals
- **MQTT Publishing**: Publishes data to MQTT broker with hierarchical topic structure
- **Persistence Integration**: Optionally fetches historical data from persistence services (e.g., InfluxDB)
- **Graceful Shutdown**: Handles SIGINT/SIGTERM signals for clean shutdown
- **Retry Logic**: Automatic retry with exponential backoff for failed MQTT publishes
- **YAML Configuration**: Easy-to-manage configuration file

## Architecture

```
openHAB Container → REST API → Exporter → MQTT Broker → Subscribers
```

The exporter:
1. Connects to openHAB REST API
2. Fetches all things and their channels
3. Collects item states and persistence data
4. Builds a hierarchical JSON payload
5. Publishes to MQTT topic: `{topic_prefix}/{site_id}/export`

## Files

- `exporter.py` - Main exporter service
- `test_mqtt_subscriber.py` - Test script to verify MQTT data flow
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container build configuration
- `__init__.py` - Package initialization

## Configuration

Configuration is managed via `configs/exporter_config.yaml`. Key settings:

### openHAB Connection
- `base_url`: openHAB instance URL (default: `http://oh:8080`)
- `timeout`: HTTP timeout in seconds
- `persistence_service`: Persistence service name (e.g., `influxdb`)
- `auth`: Authentication settings
  - `username` / `password`: Basic authentication
  - `api_token`: API token (Bearer token)

### MQTT Settings
- `broker_host`: MQTT broker hostname (default: `mqtt`)
- `broker_port`: MQTT broker port (default: `1883`)
- `topic_prefix`: Topic prefix (default: `openhab`)
- `qos`: Quality of Service level (0, 1, or 2)
- `retain`: Retain messages flag
- `username` / `password`: MQTT authentication (optional)

### Exporter Settings
- `interval_seconds`: Export interval in seconds (default: `300` = 5 minutes)
- `site_id`: Site identifier (can be set directly or loaded from file)
- `site_id_file`: Path to file containing site ID (default: `/data/site/ID`)
- `max_retries`: Maximum retry attempts for failed publishes

## Usage

### Running in Docker

The exporter is configured to run as a Docker container via `docker-compose.yml`:

```bash
# Start the exporter
sudo docker-compose --env-file config.env up -d openhab-exporter

# View logs
sudo docker logs -f openhab-exporter

# Restart the exporter
sudo docker-compose --env-file config.env restart openhab-exporter
```

### Running Manually

```bash
# Install dependencies
pip install -r requirements.txt

# Run once (test mode)
python exporter.py --once -v

# Run continuously
python exporter.py -v

# Verbose logging
python exporter.py -vv
```

### Command Line Options

- `--once`: Run a single export cycle and exit
- `-v, --verbose`: Increase logging verbosity (use multiple times for more detail)
- `--config`: Path to configuration file (default: `/app/config.yaml`)

## Testing

### Test MQTT Subscriber

Use the included test script to verify data flow:

```bash
# Install dependencies
pip install paho-mqtt

# Subscribe to all exports
python test_mqtt_subscriber.py --broker localhost --port 1883 --topic "openhab/+/export"

# Subscribe to specific site
python test_mqtt_subscriber.py --broker localhost --port 1883 --topic "openhab/GRC-10/export"
```

### Test Options

- `--broker`: MQTT broker hostname (default: `localhost`)
- `--port`: MQTT broker port (default: `1883`)
- `--topic`: Topic pattern to subscribe to (default: `openhab/+/export`)
- `--username`: MQTT username (optional)
- `--password`: MQTT password (optional)

## Payload Structure

The exporter publishes JSON payloads with the following structure:

```json
{
  "site_id": "GRC-10",
  "generated_at": "2026-02-15T08:42:55.123456+00:00",
  "things": [
    {
      "uid": "zwave:serial_zstick:705d36b14a",
      "thing_type_uid": "zwave:serial_zstick",
      "label": "Z-Wave Serial Controller",
      "location": null,
      "bridge_uid": null,
      "status": "ONLINE",
      "status_detail": "NONE",
      "channels": [
        {
          "uid": "zwave:serial_zstick:705d36b14a:serial_sof",
          "id": "serial_sof",
          "label": "Start Frames",
          "item_type": "Number",
          "kind": "STATE",
          "linked_items": [
            {
              "name": "ItemName",
              "label": "Item Label",
              "category": "category",
              "state": "ON",
              "type": "Switch",
              "group_names": ["Group1"],
              "tags": ["tag1"],
              "persistence": {
                "time": "2026-02-15T08:40:00.000Z",
                "state": "ON"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

## MQTT Topic Structure

Topics follow a hierarchical structure:
```
{topic_prefix}/{site_id}/export
```

Example:
- `openhab/GRC-10/export`
- `openhab/TEST-SITE-001/export`

## Dependencies

- `requests>=2.32.3` - HTTP client for openHAB REST API
- `paho-mqtt>=2.0.0` - MQTT client library
- `pyyaml>=6.0` - YAML configuration parser

## Troubleshooting

### Authentication Errors (401 Unauthorized)

- Verify the API token is correct in `configs/exporter_config.yaml`
- Check that the API token is active in openHAB
- Ensure the token has proper permissions

### MQTT Connection Issues

- Verify MQTT broker is running: `sudo docker ps | grep mqtt-broker`
- Check network connectivity: `ping mqtt` (from exporter container)
- Review MQTT broker logs: `sudo docker logs mqtt-broker`

### No Data Published

- Check exporter logs: `sudo docker logs openhab-exporter`
- Verify openHAB is accessible: `curl http://oh:8080/rest/things`
- Test with `--once` flag to see immediate output

### Site ID Issues

- Verify site ID file exists: `cat /data/site/ID`
- Check file is mounted in container: `sudo docker exec openhab-exporter cat /data/site/ID`
- Ensure site ID is not empty or null

## Logging

Log levels:
- `WARNING` (default): Errors and warnings only
- `INFO` (`-v`): Informational messages including successful exports
- `DEBUG` (`-vv`): Detailed debugging information

## Development

### Building the Container

```bash
sudo docker-compose --env-file config.env build openhab-exporter
```

### Running Tests

```bash
# Test exporter with verbose output
python exporter.py --once -vv

# Test MQTT subscriber
python test_mqtt_subscriber.py --broker localhost --port 1883
```

## License

Part of the Synergies-WSN-Deployment project.

