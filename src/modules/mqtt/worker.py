import os
import json
import random
import string
import time
import threading
import logging
from typing import Optional
import paho.mqtt.client as mqtt
from src.modules.mqtt.service import handle_mqtt_challenge, tracker

logger = logging.getLogger("mqtt.worker")


class MqttWorker:
    def __init__(
        self,
        broker_host: Optional[str] = None,
        broker_port: Optional[int] = None,
        candidate_id: Optional[str] = None
    ):
        self.broker_host = broker_host or os.getenv("MQTT_BROKER_HOST", "152.42.238.142")
        self.broker_port = broker_port or int(os.getenv("MQTT_BROKER_PORT", "1883"))
        self.candidate_id = candidate_id or os.getenv("CANDIDATE_ID", "default_candidate")

        rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.client_id = f"fse01-{self.candidate_id}-{rand_suffix}"

        self.challenge_topic = f"fse-01/{self.candidate_id}/challenge"
        self.response_topic = f"fse-01/{self.candidate_id}/response"
        self.status_topic = f"fse-01/{self.candidate_id}/status"

        tracker.candidate_id = self.candidate_id
        tracker.broker = f"{self.broker_host}:{self.broker_port}"

        self.client: Optional[mqtt.Client] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _setup_client(self):
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False
        )

        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        # Last will: OFFLINE on status topic
        self.client.will_set(self.status_topic, payload="OFFLINE", qos=1, retain=False)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}. Subscribing to {self.challenge_topic}")
            client.subscribe(self.challenge_topic, qos=1)
        else:
            logger.warning(f"MQTT connect failed with reason code: {reason_code}")
            tracker.connected = False

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        logger.info(f"Subscription to {self.challenge_topic} confirmed. Publishing ONLINE to {self.status_topic}")
        client.publish(self.status_topic, payload="ONLINE", qos=1, retain=False)
        tracker.connected = True

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.info(f"Disconnected from MQTT broker. Reason code: {reason_code}")
        tracker.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            logger.info(f"Received MQTT challenge on {msg.topic}")
            resp = handle_mqtt_challenge(msg.payload, self.candidate_id)
            payload_str = json.dumps(resp)
            client.publish(self.response_topic, payload=payload_str, qos=1, retain=False)
            logger.info(f"Published response for challenge {resp.get('challenge_id')} to {self.response_topic}")
        except Exception as e:
            logger.error(f"Error in on_message: {e}", exc_info=True)

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(20)
            if self._running and self.client and tracker.connected:
                try:
                    self.client.publish(self.status_topic, payload="HEARTBEAT", qos=1, retain=False)
                except Exception as e:
                    logger.debug(f"Heartbeat send failed: {e}")

    def start(self):
        logger.info(f"Starting MQTT worker for candidate {self.candidate_id}...")
        self._setup_client()
        self._running = True
        try:
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()

            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="mqtt-heartbeat")
            self._heartbeat_thread.start()
        except Exception as e:
            logger.error(f"Failed to start MQTT client: {e}")

    def stop(self):
        logger.info("Stopping MQTT worker...")
        self._running = False
        if self.client:
            try:
                if tracker.connected:
                    self.client.publish(self.status_topic, payload="OFFLINE", qos=1, retain=False)
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logger.debug(f"Error during MQTT shutdown: {e}")
        tracker.connected = False


_worker: Optional[MqttWorker] = None


def get_worker() -> Optional[MqttWorker]:
    global _worker
    return _worker


def start_mqtt_worker() -> MqttWorker:
    global _worker
    if _worker is None:
        _worker = MqttWorker()
        _worker.start()
    return _worker


def stop_mqtt_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
