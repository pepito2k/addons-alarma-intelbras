# Archivo: addon_main.py (v3.4 - Sensores detallados y Pánico)
import logging
import os
import signal
import sys
import threading
import time

import paho.mqtt.client as mqtt
from mqtt_runtime import MQTTRuntime
from protocol_handlers import create_protocol_handler

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] - %(levelname)s - %(message)s', stream=sys.stdout)

# --- Configuración ---
ALARM_IP = os.environ.get('ALARM_IP')
ALARM_PORT = int(os.environ.get('ALARM_PORT', 9009))
ALARM_PASS = os.environ.get('ALARM_PASS')
ALARM_PROTOCOL = os.environ.get('ALARM_PROTOCOL', 'isecnet').lower()

MQTT_BROKER = os.environ.get('MQTT_BROKER')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
MQTT_USER = os.environ.get('MQTT_USER')
MQTT_PASS = os.environ.get('MQTT_PASS')

POLLING_INTERVAL_MINUTES = max(1, int(os.environ.get('POLLING_INTERVAL_MINUTES', 5)))
ZONE_RANGE = os.environ.get('ZONE_RANGE', '').strip()
ZONE_COUNT = int(os.environ.get('ZONE_COUNT', 0))
PASSWORD_LENGTH = int(os.environ.get('PASSWORD_LENGTH', 0) or 0)

AVAILABILITY_TOPIC = "intelbras/alarm/availability"
COMMAND_TOPIC = "intelbras/alarm/command"
BASE_TOPIC = "intelbras/alarm"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
shutdown_event = threading.Event()
alarm_lock = threading.Lock()

# --- Almacén Central de Estados ---
def _parse_zone_ids(zone_range, fallback_count):
    if zone_range:
        try:
            zone_ids = []
            for part in zone_range.split(","):
                token = part.strip()
                if not token:
                    continue
                if "-" in token:
                    start_str, end_str = token.split("-", 1)
                    start = int(start_str)
                    end = int(end_str)
                    if end < start:
                        start, end = end, start
                    zone_ids.extend(range(start, end + 1))
                else:
                    zone_ids.append(int(token))
            zone_ids = sorted(set(zone_ids))
            if zone_ids:
                return zone_ids
        except ValueError:
            logging.warning(f"ZONE_RANGE inválido '{zone_range}', usando ZONE_COUNT.")
    return list(range(1, max(0, fallback_count) + 1))


ZONE_IDS = _parse_zone_ids(ZONE_RANGE, ZONE_COUNT)
zone_states = {str(i): "Desconocido" for i in ZONE_IDS}

protocol_handler = None


def get_protocol_handler():
    return protocol_handler


mqtt_runtime = MQTTRuntime(
    mqtt_client=mqtt_client,
    base_topic=BASE_TOPIC,
    command_topic=COMMAND_TOPIC,
    availability_topic=AVAILABILITY_TOPIC,
    zone_states=zone_states,
    alarm_lock=alarm_lock,
    protocol_handler_getter=get_protocol_handler,
)


def status_polling_thread():
    logging.info(f"Iniciando sondeo cada {POLLING_INTERVAL_MINUTES} minutos.")
    while not shutdown_event.is_set():
        with alarm_lock:
            if protocol_handler is not None:
                protocol_handler.poll_status()
                mqtt_runtime.publish_zone_states()
        shutdown_event.wait(POLLING_INTERVAL_MINUTES * 60)
    logging.info("Hilo de sondeo terminado.")


def handle_shutdown(signum, frame):
    logging.info("Cerrando addon...")
    shutdown_event.set()

    mqtt_runtime.publish_offline()
    time.sleep(1)
    mqtt_client.loop_stop()

    if protocol_handler is not None:
        protocol_handler.shutdown()

    sys.exit(0)


if __name__ == "__main__":
    protocol_handler = create_protocol_handler(
        protocol=ALARM_PROTOCOL,
        alarm_ip=ALARM_IP,
        alarm_port=ALARM_PORT,
        alarm_pass=ALARM_PASS,
        password_length=PASSWORD_LENGTH,
        mqtt_client=mqtt_client,
        base_topic=BASE_TOPIC,
        zone_states=zone_states,
        alarm_lock=alarm_lock,
        publish_zone_states=mqtt_runtime.publish_zone_states,
        publish_triggered_zones_state=mqtt_runtime.publish_triggered_zones_state,
    )

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    ok, startup_error = protocol_handler.validate_startup(ALARM_IP, MQTT_BROKER)
    if not ok:
        logging.error(startup_error)
        sys.exit(1)

    mqtt_runtime.configure_client()
    if MQTT_USER:
        mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as exc:
        logging.error(f"Fallo al conectar a MQTT: {exc}")
        sys.exit(1)

    mqtt_client.loop_start()
    try:
        protocol_handler.start()
    except RuntimeError as exc:
        logging.error(str(exc))
        sys.exit(1)

    threading.Thread(target=status_polling_thread, daemon=True).start()

    logging.info("Addon en funcionamiento. Esperando eventos...")
    shutdown_event.wait()
