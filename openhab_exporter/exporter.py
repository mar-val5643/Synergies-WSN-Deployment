#!/usr/bin/env python3
"""
openHAB Exporter

Periodically collects the latest state for all items grouped by thing/channel
and forwards the payload to a remote HTTP endpoint.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import paho.mqtt.client as mqtt

import requests
from requests import Response, Session


LOGGER = logging.getLogger("openhab-exporter")


class GracefulExit(SystemExit):
    """Raised when a termination signal is received."""


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


def _current_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_site_id(site_id_env: Optional[str]) -> Optional[str]:
    if site_id_env:
        return site_id_env.strip() or None
    return None

def _merge_dict(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    merged.update(extra)
    return merged


class OpenHABClient:
    def __init__(
        self,
        base_url: str,
        session: Session,
        timeout: float,
        persistence_service: Optional[str],
        api_token: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout = timeout
        self.persistence_service = persistence_service
        self.api_token = api_token

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Accept", "application/json")
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return self.session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

    def fetch_things(self) -> List[Dict[str, Any]]:
        resp = self._request("GET", "/rest/things")
        resp.raise_for_status()
        return resp.json()

    def fetch_item(self, name: str) -> Dict[str, Any]:
        resp = self._request("GET", f"/rest/items/{name}")
        resp.raise_for_status()
        return resp.json()

    def fetch_persistence_snapshot(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.persistence_service:
            return None

        params = {"pageSize": 1}
        if self.persistence_service:
            params["serviceId"] = self.persistence_service

        resp = self._request("GET", f"/rest/persistence/items/{name}", params=params)
        if resp.status_code == 200:
            body = resp.json()
            data_points: Iterable[Dict[str, Any]] = body.get("data", [])
            # The API returns a list with the earliest entry first; the last entry is the latest snapshot.
            last_point = None
            for entry in data_points:
                last_point = entry
            if last_point:
                return {
                    "time": last_point.get("time"),
                    "state": last_point.get("state"),
                }
            # Some persistence services provide last value fields
            if "lastUpdate" in body and "lastValue" in body:
                return {
                    "time": body.get("lastUpdate"),
                    "state": body.get("lastValue"),
                }
        return None


class Exporter:
    def __init__(
        self,
        site_id: Optional[str],
        client: OpenHABClient,
        interval: float,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_user: Optional[str] = None,
        mqtt_pass: Optional[str] = None,
    ) -> None:
        self.site_id = site_id
        self.client = client
        self.interval = interval
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if mqtt_user:
            self.mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
        self.mqtt_client.connect(mqtt_host, mqtt_port)
        self.mqtt_client.loop_start()

    def build_payload(self) -> Dict[str, Any]:
        things = self.client.fetch_things()
        item_cache: Dict[str, Dict[str, Any]] = {}
        hierarchy: List[Dict[str, Any]] = []

        for thing in things:
            channels_output: List[Dict[str, Any]] = []
            for channel in thing.get("channels", []):
                linked_items = []
                for item_name in channel.get("linkedItems", []):
                    item_payload = item_cache.get(item_name)
                    if not item_payload:
                        item_payload = self._format_item(item_name)
                        item_cache[item_name] = item_payload
                    linked_items.append(dict(item_payload))

                channels_output.append(
                    {
                        "uid": channel.get("uid"),
                        "id": channel.get("id"),
                        "label": channel.get("label"),
                        "item_type": channel.get("itemType"),
                        "kind": channel.get("kind"),
                        "linked_items": linked_items,
                    }
                )

            hierarchy.append(
                {
                    "uid": thing.get("UID"),
                    "thing_type_uid": thing.get("thingTypeUID"),
                    "label": thing.get("label"),
                    "location": thing.get("location"),
                    "bridge_uid": thing.get("bridgeUID"),
                    "status": thing.get("statusInfo", {}).get("status"),
                    "status_detail": thing.get("statusInfo", {}).get("statusDetail"),
                    "channels": channels_output,
                }
            )

        payload = {
            "site_id": self.site_id,
            "generated_at": _current_ts(),
            "things": hierarchy,
        }
        return payload

    def _format_item(self, item_name: str) -> Dict[str, Any]:
        item = self.client.fetch_item(item_name)
        item_payload = {
            "name": item.get("name"),
            "label": item.get("label"),
            "category": item.get("category"),
            "state": item.get("state"),
            "type": item.get("type"),
            "group_names": item.get("groupNames", []),
            "tags": item.get("tags", []),
        }

        persistence_snapshot = self.client.fetch_persistence_snapshot(item_name)
        if persistence_snapshot:
            item_payload["persistence"] = persistence_snapshot

        return item_payload

    def send_payload(self, payload: Dict[str, Any]) -> None:
        site_id = payload.get("site_id", "unknown")
        generated_at = payload.get("generated_at")
        
        for thing in payload.get("things", []):
            clean_uid = thing.get("uid", "unknown").replace(":", "_")
            topic = f"openhab/{site_id}/devices/{clean_uid}"
            
            device_payload = {
                "site_id": site_id,
                "generated_at": generated_at,
                "thing": thing
            }
            
            data = json.dumps(device_payload, ensure_ascii=False)
            result = self.mqtt_client.publish(topic, data, qos=1, retain=True)
            result.wait_for_publish()
            LOGGER.info("Published device %s to topic: %s", clean_uid, topic)

    def run_forever(self, run_once: bool = False) -> None:
        while True:
            try:
                payload = self.build_payload()
                self.send_payload(payload)

                if run_once:
                    return

                LOGGER.debug("Sleeping for %s seconds", self.interval)
                time.sleep(self.interval)
            except Exception as exc:
                LOGGER.error("Exporter loop encountered an error: %s", exc)
                if run_once:
                    break
                time.sleep(10)


def build_session(username: Optional[str], password: Optional[str], verify_tls: bool) -> Session:
    session = requests.Session()
    if username:
        session.auth = (username, password or "")
    session.verify = verify_tls
    return session


def _handle_signals():
    def _raise_graceful_exit(signum, _frame):
        raise GracefulExit(f"Received signal {signum}")

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _raise_graceful_exit)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="openHAB measurements exporter")
    parser.add_argument("--once", action="store_true", help="Run a single collection/post cycle and exit")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase logging verbosity")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)
    _handle_signals()

    openhab_url = os.getenv("OH_BASE_URL", "http://oh:8080")
    api_token = os.getenv("OH_TOKEN")
    
    site_id = _load_site_id(os.getenv("SITE_ID"))
    if not site_id:
        LOGGER.warning("No SITE_ID found in environment.")
    
    mqtt_host = os.getenv("MQTT_HOST", "mqtt")  
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_user = os.getenv("MQTT_USERNAME")     
    mqtt_pass = os.getenv("MQTT_PASSWORD")  
    
    interval = float(os.getenv("EXPORTER_INTERVAL_SECONDS", "300"))
    persistence_service = os.getenv("OPENHAB_PERSISTENCE_SERVICE", "influxdb") or None

    openhab_timeout = float(os.getenv("OPENHAB_HTTP_TIMEOUT_SECONDS", "10"))
    verify_tls_env = os.getenv("OPENHAB_TLS_VERIFY", "true").lower()
    verify_tls = verify_tls_env not in ("0", "false", "no")

    username = os.getenv("OPENHAB_USERNAME")
    password = os.getenv("OPENHAB_PASSWORD")

    session = build_session(username, password, verify_tls)
    client = OpenHABClient(openhab_url, session, openhab_timeout, persistence_service, api_token=api_token)
    exporter = Exporter(
        site_id=site_id, 
        client=client, 
        interval=interval, 
        mqtt_host=mqtt_host, 
        mqtt_port=mqtt_port, 
        mqtt_user=mqtt_user, 
        mqtt_pass=mqtt_pass
    )

    try:
        exporter.run_forever(run_once=args.once)
    except GracefulExit as exc:
        LOGGER.info("Exporter exiting gracefully: %s", exc)
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected exporter failure")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

