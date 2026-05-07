#!/usr/bin/env python3
"""
MQTT Test Subscriber for openHAB Exporter

Connects to an MQTT broker and subscribes to openHAB exporter topics
to verify data flow and validate payload structure.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


class MQTTSubscriber:
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        topic_pattern: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_pattern = topic_pattern
        self.username = username
        self.password = password
        
        self.client: Optional[mqtt.Client] = None
        self.message_count = 0
        self.last_message_time: Optional[datetime] = None
        self.running = True

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], *args, **kwargs) -> None:
        """Callback for MQTT connection."""
        # Handle both VERSION1 (rc as 4th arg) and VERSION2 (reason_code as keyword)
        if args:
            rc = args[0]  # VERSION1
        else:
            rc = kwargs.get('reason_code', 0)  # VERSION2
        
        if rc == 0:
            print(f"[{_current_ts()}] Connected to MQTT broker {self.broker_host}:{self.broker_port}")
            print(f"[{_current_ts()}] Subscribing to topic pattern: {self.topic_pattern}")
            client.subscribe(self.topic_pattern, qos=1)
        else:
            print(f"[{_current_ts()}] Failed to connect to MQTT broker (code {rc})")
            self.running = False

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, *args, **kwargs) -> None:
        """Callback for MQTT disconnection."""
        # Handle both VERSION1 (rc as 3rd arg) and VERSION2 (reason_code as keyword)
        if args:
            rc = args[0]  # VERSION1
        else:
            rc = kwargs.get('reason_code', 0)  # VERSION2
        
        if rc != 0:
            print(f"[{_current_ts()}] Unexpected disconnection from MQTT broker (code {rc})")
        else:
            print(f"[{_current_ts()}] Disconnected from MQTT broker")

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        """Callback for received MQTT messages."""
        self.message_count += 1
        self.last_message_time = datetime.now(timezone.utc)
        
        timestamp = _current_ts()
        topic = msg.topic
        payload_size = len(msg.payload)
        
        print(f"\n{'='*80}")
        print(f"[{timestamp}] Message #{self.message_count} received")
        print(f"Topic: {topic}")
        print(f"Payload size: {payload_size} bytes")
        print(f"QoS: {msg.qos}")
        print(f"{'='*80}")
        
        # Try to parse as JSON
        try:
            payload_str = msg.payload.decode("utf-8")
            payload_data = json.loads(payload_str)
            
            # Validate payload structure
            validation_result = _validate_payload(payload_data)
            if validation_result["valid"]:
                print("✓ Payload structure is valid")
            else:
                print(f"✗ Payload validation failed: {validation_result['error']}")
            
            # Pretty print JSON
            print("\nPayload content:")
            print(json.dumps(payload_data, indent=2, ensure_ascii=False))
            
            # Print summary statistics
            if isinstance(payload_data, dict):
                things_count = len(payload_data.get("things", []))
                site_id = payload_data.get("site_id", "N/A")
                generated_at = payload_data.get("generated_at", "N/A")
                
                print(f"\nSummary:")
                print(f"  Site ID: {site_id}")
                print(f"  Generated at: {generated_at}")
                print(f"  Number of things: {things_count}")
                
        except UnicodeDecodeError as exc:
            print(f"✗ Failed to decode payload as UTF-8: {exc}")
            print(f"Raw payload (first 200 bytes): {msg.payload[:200]}")
        except json.JSONDecodeError as exc:
            print(f"✗ Failed to parse payload as JSON: {exc}")
            print(f"Payload preview: {msg.payload[:200].decode('utf-8', errors='replace')}")
        except Exception as exc:
            print(f"✗ Unexpected error processing message: {exc}")
        
        print(f"\nTotal messages received: {self.message_count}")
        if self.last_message_time:
            print(f"Last message time: {self.last_message_time.isoformat()}")

    def _on_subscribe(self, client: mqtt.Client, userdata: Any, mid: int, *args, **kwargs) -> None:
        """Callback for subscription confirmation."""
        # Handle both VERSION1 (granted_qos as 4th arg) and VERSION2 (properties as keyword)
        if args:
            granted_qos = args[0]  # VERSION1
        else:
            # VERSION2 uses properties, extract granted_qos from there
            properties = kwargs.get('properties', {})
            granted_qos = properties.get('reasonString', 'unknown')
        
        print(f"[{_current_ts()}] Subscribed to topic pattern (mid: {mid}, QoS: {granted_qos})")
        print(f"[{_current_ts()}] Waiting for messages... (Press Ctrl+C to exit)")

    def run(self) -> None:
        """Run the MQTT subscriber."""
        # Create MQTT client with VERSION2 to avoid deprecation warning
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            # Fallback for older paho-mqtt versions
            self.client = mqtt.Client()
        
        # Set authentication if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        
        # Connect to broker
        try:
            print(f"[{_current_ts()}] Connecting to MQTT broker {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            
            # Start network loop
            self.client.loop_start()
            
            # Keep running until interrupted
            while self.running:
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print(f"\n[{_current_ts()}] Interrupted by user")
        except Exception as exc:
            print(f"[{_current_ts()}] Error: {exc}")
        finally:
            # Clean up
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
            
            # Print final statistics
            print(f"\n{'='*80}")
            print("Final Statistics:")
            print(f"  Total messages received: {self.message_count}")
            if self.last_message_time:
                print(f"  Last message time: {self.last_message_time.isoformat()}")
            print(f"{'='*80}")


def _current_ts() -> str:
    """Get current timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_payload(payload: Any) -> Dict[str, Any]:
    """Validate payload structure."""
    if not isinstance(payload, dict):
        return {"valid": False, "error": "Payload is not a dictionary"}
    
    # Check required top-level fields
    required_fields = ["generated_at", "things"]
    for field in required_fields:
        if field not in payload:
            return {"valid": False, "error": f"Missing required field: {field}"}
    
    # Validate things is a list
    if not isinstance(payload["things"], list):
        return {"valid": False, "error": "Field 'things' must be a list"}
    
    # Validate each thing has required fields
    for i, thing in enumerate(payload["things"]):
        if not isinstance(thing, dict):
            return {"valid": False, "error": f"Thing at index {i} is not a dictionary"}
        
        if "uid" not in thing:
            return {"valid": False, "error": f"Thing at index {i} missing 'uid' field"}
        
        if "channels" not in thing:
            return {"valid": False, "error": f"Thing at index {i} missing 'channels' field"}
        
        if not isinstance(thing["channels"], list):
            return {"valid": False, "error": f"Thing at index {i} 'channels' must be a list"}
    
    return {"valid": True}


def _handle_signals(subscriber: MQTTSubscriber) -> None:
    """Set up signal handlers for graceful shutdown."""
    def _signal_handler(signum, _frame):
        print(f"\n[{_current_ts()}] Received signal {signum}, shutting down...")
        subscriber.running = False
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MQTT test subscriber for openHAB exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Subscribe to all openHAB exports
  python test_mqtt_subscriber.py --broker mqtt-broker --port 1883

  # Subscribe to specific site
  python test_mqtt_subscriber.py --broker localhost --port 1883 --topic "openhab/GRC-XXX/export"

  # With authentication
  python test_mqtt_subscriber.py --broker mqtt-broker --port 1883 --username user --password pass
        """,
    )
    parser.add_argument(
        "--broker",
        default="localhost",
        help="MQTT broker hostname or IP (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--topic",
        default="openhab/+/export",
        help="MQTT topic pattern to subscribe to (default: openhab/+/export)",
    )
    parser.add_argument(
        "--username",
        help="MQTT username (optional)",
    )
    parser.add_argument(
        "--password",
        help="MQTT password (optional, required if username is provided)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    
    # Validate password if username is provided
    if args.username and not args.password:
        print("Error: Password is required when username is provided", file=sys.stderr)
        return 1
    
    # Create subscriber
    subscriber = MQTTSubscriber(
        broker_host=args.broker,
        broker_port=args.port,
        topic_pattern=args.topic,
        username=args.username,
        password=args.password,
    )
    
    # Set up signal handlers
    _handle_signals(subscriber)
    
    # Run subscriber
    try:
        subscriber.run()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

