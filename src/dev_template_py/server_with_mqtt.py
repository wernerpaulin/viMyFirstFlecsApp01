import logging
import os
import json
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from dev_template_py.example import add_numbers

logger = logging.getLogger(__name__)

class BelowErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.ERROR


# --- FastAPI
class AddParameters(BaseModel):
    left: float
    right: float

app = FastAPI(title="MyApp API", version="1.0")

@app.post("/add")
async def handle_post_add(params: AddParameters):
    logger.info("/add endpoint accessed")
    return {"result": add_numbers(params.left, params.right)}


# --- MQTT (WICHTIG: Imports + Setup in startup, nicht Top-Level connect)
mqtt_client = None

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_ADD = os.getenv("MQTT_TOPIC_ADD", "add")
TOPIC_RESULT = os.getenv("MQTT_TOPIC_RESULT", "result")

def _safe_json_loads(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload must be JSON object")
    return data

@app.on_event("startup")
def mqtt_startup():
    global mqtt_client

    # Import hier, damit ein evtl. Missing-Dependency nicht das Logging-Setup “zerlegt”
    import paho.mqtt.client as mqtt

    def on_connect(client, userdata, flags, rc):
        if rc != 0:
            logger.error("MQTT connect failed rc=%s", rc)
            return
        client.subscribe(TOPIC_ADD)
        logger.info('MQTT subscribed "%s"', TOPIC_ADD)

    def on_message(client, userdata, msg):
        try:
            data = _safe_json_loads(msg.payload)
            left = float(data["left"])
            right = float(data["right"])
            result = add_numbers(left, right)
            client.publish(TOPIC_RESULT, json.dumps({"result": result}))
        except Exception:
            logger.exception("MQTT message handling failed")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    mqtt_client = client

@app.on_event("shutdown")
def mqtt_shutdown():
    global mqtt_client
    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        mqtt_client = None
