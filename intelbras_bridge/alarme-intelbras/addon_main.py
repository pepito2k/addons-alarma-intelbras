# Archivo: addon_main.py (v3.4 - Sensores detallados y Pánico)
import logging
import os
import signal
import sys
import threading
import time

import paho.mqtt.client as mqtt
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
ZONE_COUNT = int(os.environ.get('ZONE_COUNT', 0))
PASSWORD_LENGTH = int(os.environ.get('PASSWORD_LENGTH', 0) or 0)

AVAILABILITY_TOPIC = "intelbras/alarm/availability"
COMMAND_TOPIC = "intelbras/alarm/command"
BASE_TOPIC = "intelbras/alarm"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
shutdown_event = threading.Event()
alarm_lock = threading.Lock()

# --- Almacén Central de Estados ---
zone_states = {str(i): "Desconocido" for i in range(1, ZONE_COUNT + 1)}

protocol_handler = None


# --- Funciones de MQTT ---
def publish_zone_states():
    for zone_id, state in zone_states.items():
        mqtt_client.publish(f"{BASE_TOPIC}/zone_{zone_id}", state, retain=True)
    logging.info(f"Estados de zona publicados a MQTT: {zone_states}")


def _current_triggered_zone_ids() -> list[str]:
    return sorted([zone_id for zone_id, state in zone_states.items() if state == "Disparada"], key=int)


def publish_triggered_zones_state():
    triggered = _current_triggered_zone_ids()
    mqtt_client.publish(
        f"{BASE_TOPIC}/triggered_zones",
        ",".join(triggered) if triggered else "Ninguna",
        retain=True,
    )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logging.info("Conectado a MQTT y suscrito.")
        client.subscribe(COMMAND_TOPIC)
        client.publish(AVAILABILITY_TOPIC, "online", retain=True)
        client.publish(f"{BASE_TOPIC}/ac_power", "on", retain=True)
        client.publish(f"{BASE_TOPIC}/system_battery", "off", retain=True)
        client.publish(f"{BASE_TOPIC}/tamper", "off", retain=True)
        client.publish(f"{BASE_TOPIC}/panic", "off", retain=True)
        client.publish(f"{BASE_TOPIC}/triggered_zones", "Ninguna", retain=True)
        client.publish(f"{BASE_TOPIC}/partition_a_state", "OFF", retain=True)
        client.publish(f"{BASE_TOPIC}/partition_b_state", "OFF", retain=True)
        client.publish(f"{BASE_TOPIC}/partition_c_state", "OFF", retain=True)
        client.publish(f"{BASE_TOPIC}/partition_d_state", "OFF", retain=True)
        publish_zone_states()
    else:
        logging.error(f"Fallo al conectar a MQTT: {reason_code}")


def on_message(client, userdata, msg):
    command = msg.payload.decode()
    logging.info(f"Comando MQTT recibido: '{command}'")
    with alarm_lock:
        if protocol_handler is None:
            logging.error("Handler de protocolo no inicializado.")
            return
        protocol_handler.handle_command(command)


def status_polling_thread():
    logging.info(f"Iniciando sondeo cada {POLLING_INTERVAL_MINUTES} minutos.")
    while not shutdown_event.is_set():
        with alarm_lock:
            if protocol_handler is not None:
                protocol_handler.poll_status()
                publish_zone_states()
        shutdown_event.wait(POLLING_INTERVAL_MINUTES * 60)
    logging.info("Hilo de sondeo terminado.")


def handle_shutdown(signum, frame):
    logging.info("Cerrando addon...")
    shutdown_event.set()

    mqtt_client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
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
        zone_count=ZONE_COUNT,
        alarm_lock=alarm_lock,
        publish_zone_states=publish_zone_states,
        publish_triggered_zones_state=publish_triggered_zones_state,
    )

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    ok, startup_error = protocol_handler.validate_startup(ALARM_IP, MQTT_BROKER)
    if not ok:
        logging.error(startup_error)
        sys.exit(1)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
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
