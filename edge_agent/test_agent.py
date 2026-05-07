#!/usr/bin/env python3
"""
Test script to interact with edge agent via MQTT.
Provides functions to get all things and get last value of items.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt


def load_site_id(site_id: Optional[str] = None, site_id_file: Optional[str] = None) -> Optional[str]:
    """Load site ID from direct value, file, or environment variable."""
    # Use direct value if provided
    if site_id:
        return site_id.strip() if isinstance(site_id, str) else None
    
    # Try environment variable
    env_site_id = os.getenv("SITE_ID")
    if env_site_id:
        return env_site_id.strip()
    
    # Try reading from file
    if site_id_file:
        path = Path(site_id_file)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip() or None
            except OSError as exc:
                logging.warning("Failed to read site_id file %s: %s", path, exc)
    
    # Try default file location
    default_file = Path("/data/site/ID")
    if default_file.exists():
        try:
            return default_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
    
    return None


def send_command(
    client: mqtt.Client,
    command_topic: str,
    response_topic: str,
    method: str,
    endpoint: str,
    data: Optional[str] = None,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Send a command to the edge agent via MQTT and wait for response.
    
    Args:
        client: MQTT client (must be connected and subscribed to response_topic)
        command_topic: MQTT topic to publish commands to
        response_topic: MQTT topic to receive responses from
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: openHAB REST API endpoint
        data: Optional request body data
        timeout: Seconds to wait for response
    
    Returns:
        Response dictionary or None if timeout
    """
    response_queue: queue.Queue[dict] = queue.Queue()
    correlation_id = str(uuid.uuid4())
    
    def on_message(_client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except json.JSONDecodeError:
            logging.warning("Received non-JSON response: %s", message.payload)
            return
        if payload.get("correlation_id") == correlation_id:
            response_queue.put(payload)
    
    # Temporarily set message handler
    original_handler = client.on_message
    client.on_message = on_message
    
    try:
        command_payload = {
            "method": method,
            "endpoint": endpoint,
            "data": data,
            "correlation_id": correlation_id,
            "idempotency_key": f"{correlation_id}:{int(datetime.now(timezone.utc).timestamp())}",
        }
        
        logging.debug("Publishing command: %s", json.dumps(command_payload))
        result = client.publish(command_topic, json.dumps(command_payload), qos=1, retain=False)
        
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logging.error("Failed to publish command: %s", result.rc)
            return None
        
        try:
            response = response_queue.get(timeout=timeout)
            return response
        except queue.Empty:
            logging.error("Timed out waiting for response with correlation_id %s", correlation_id)
            return None
    finally:
        client.on_message = original_handler


def get_all_things(
    client: mqtt.Client,
    command_topic: str,
    response_topic: str,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Get all things from openHAB via edge agent.
    
    Returns:
        Response dictionary containing things list or None on error
    """
    logging.info("Requesting all things from openHAB...")
    response = send_command(
        client=client,
        command_topic=command_topic,
        response_topic=response_topic,
        method="GET",
        endpoint="/rest/things",
        timeout=timeout,
    )
    
    if response:
        if response.get("status_code") == 200:
            logging.info("Successfully retrieved things")
            return response
        else:
            logging.error("Failed to get things: status_code=%d, error=%s", 
                         response.get("status_code"), response.get("error"))
    return None


def get_item_last_value(
    client: mqtt.Client,
    command_topic: str,
    response_topic: str,
    item_name: str,
    persistence_service: str = "influxdb",
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Get the last persisted value of an item from openHAB via edge agent.
    
    Args:
        client: MQTT client
        command_topic: MQTT command topic
        response_topic: MQTT response topic
        item_name: Name of the item
        persistence_service: Persistence service name (default: influxdb)
        timeout: Response timeout in seconds
    
    Returns:
        Response dictionary containing last value or None on error
    """
    logging.info("Requesting last value for item '%s' from openHAB...", item_name)
    
    # Build endpoint with query parameters
    endpoint = f"/rest/persistence/items/{item_name}?serviceId={persistence_service}&pageSize=1"
    
    response = send_command(
        client=client,
        command_topic=command_topic,
        response_topic=response_topic,
        method="GET",
        endpoint=endpoint,
        timeout=timeout,
    )
    
    if response:
        if response.get("status_code") == 200:
            logging.info("Successfully retrieved last value for item '%s'", item_name)
            return response
        else:
            logging.error("Failed to get last value: status_code=%d, error=%s",
                         response.get("status_code"), response.get("error"))
    return None


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Test script to interact with edge agent via MQTT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get all things
  %(prog)s --host localhost --port 1883 get-things
  
  # Get last value of an item
  %(prog)s --host localhost --port 1883 get-last-value --item MyItemName
  
  # With site ID from file
  %(prog)s --host localhost --port 1883 --site-id-file /data/site/ID get-things
        """
    )
    
    # Connection arguments
    parser.add_argument("--host", default="localhost", help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--username", help="MQTT username")
    parser.add_argument("--password", help="MQTT password")
    parser.add_argument("--tls", action="store_true", help="Use TLS (default: false)")
    parser.add_argument("--ca-cert", help="CA certificate path for TLS validation")
    
    # Site ID arguments
    parser.add_argument("--site-id", help="Site ID (overrides file and env var)")
    parser.add_argument("--site-id-file", help="Path to file containing site ID (default: /data/site/ID)")
    
    # Topic prefix
    parser.add_argument("--topic-prefix", default="openhab", help="Topic prefix (default: openhab)")
    
    # Timeout
    parser.add_argument("--timeout", type=int, default=10, help="Response timeout in seconds (default: 10)")
    
    # Verbosity
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute", required=True)
    
    # get-things command
    get_things_parser = subparsers.add_parser("get-things", help="Get all things from openHAB")
    
    # get-last-value command
    get_value_parser = subparsers.add_parser("get-last-value", help="Get last persisted value of an item")
    get_value_parser.add_argument("--item", required=True, help="Item name")
    get_value_parser.add_argument("--persistence-service", default="influxdb", 
                                  help="Persistence service name (default: influxdb)")
    
    return parser


def main() -> int:
    """Main entry point."""
    args = build_parser().parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Load site ID
    site_id = load_site_id(args.site_id, args.site_id_file)
    if not site_id:
        logging.error("Site ID not found. Provide --site-id, set SITE_ID env var, or ensure /data/site/ID exists")
        return 1
    
    logging.info("Using site ID: %s", site_id)
    
    # Build topics
    topic_prefix = args.topic_prefix
    command_topic = f"{topic_prefix}/{site_id}/command"
    response_topic = f"{topic_prefix}/{site_id}/response"
    
    logging.info("Command topic: %s", command_topic)
    logging.info("Response topic: %s", response_topic)
    
    # Create MQTT client
    client_id = f"test-agent-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(client_id=client_id, clean_session=True)
    
    if args.username:
        client.username_pw_set(args.username, args.password)
    
    if args.tls:
        client.tls_set(ca_certs=args.ca_cert)
        client.tls_insecure_set(False)
    
    # Connect to broker
    try:
        logging.info("Connecting to MQTT broker %s:%d...", args.host, args.port)
        client.connect(args.host, args.port, keepalive=60)
        client.subscribe(response_topic, qos=1)
        client.loop_start()
        
        # Wait a moment for subscription to be established
        import time
        time.sleep(0.5)
        
        # Execute command
        if args.command == "get-things":
            response = get_all_things(client, command_topic, response_topic, args.timeout)
            if response:
                print("\n" + "=" * 80)
                print("Response:")
                print("=" * 80)
                print(json.dumps(response, indent=2))
                if response.get("status_code") == 200:
                    data = response.get("data", [])
                    if isinstance(data, list):
                        print(f"\nFound {len(data)} thing(s)")
                    return 0
                return 1
            return 1
        
        elif args.command == "get-last-value":
            response = get_item_last_value(
                client, command_topic, response_topic, 
                args.item, args.persistence_service, args.timeout
            )
            if response:
                print("\n" + "=" * 80)
                print("Response:")
                print("=" * 80)
                print(json.dumps(response, indent=2))
                if response.get("status_code") == 200:
                    data = response.get("data", {})
                    if isinstance(data, dict):
                        # Try to extract last value
                        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                            last_entry = data["data"][-1]
                            print(f"\nLast value: {last_entry.get('state')} at {last_entry.get('time')}")
                        elif "lastValue" in data:
                            print(f"\nLast value: {data.get('lastValue')} at {data.get('lastUpdate')}")
                    return 0
                return 1
            return 1
        
        else:
            logging.error("Unknown command: %s", args.command)
            return 1
    
    except Exception as exc:
        logging.exception("Error: %s", exc)
        return 1
    
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())

