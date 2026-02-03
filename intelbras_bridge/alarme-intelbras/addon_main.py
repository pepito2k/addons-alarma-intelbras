# Archivo: addon_main.py (v3.4 - Sensores detallados y Pánico)
import os, sys, logging, subprocess, threading, signal, time, asyncio
import paho.mqtt.client as mqtt
from client import Client as AlarmClient, CommunicationError, AuthError
from isecnet.server import AMTServer, AMTServerConfig
from isecnet.protocol.commands import (
    ActivationCommand,
    DeactivationCommand,
    SirenCommand,
    StatusRequestCommand,
)
from isecnet.protocol.commands.status import CentralStatus, PartialCentralStatus
from isecnet.protocol.responses import ResponseType

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] - %(levelname)s - %(message)s', stream=sys.stdout)

# --- Configuración ---
ALARM_IP = os.environ.get('ALARM_IP'); ALARM_PORT = int(os.environ.get('ALARM_PORT', 9009)); ALARM_PASS = os.environ.get('ALARM_PASS')
ALARM_PROTOCOL = os.environ.get('ALARM_PROTOCOL', 'isecnet').lower()
MQTT_BROKER = os.environ.get('MQTT_BROKER'); MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883)); MQTT_USER = os.environ.get('MQTT_USER'); MQTT_PASS = os.environ.get('MQTT_PASS')
POLLING_INTERVAL_MINUTES = int(os.environ.get('POLLING_INTERVAL_MINUTES', 5))
ZONE_COUNT = int(os.environ.get('ZONE_COUNT', 0))
PASSWORD_LENGTH = int(os.environ.get('PASSWORD_LENGTH', 0) or 0)
AVAILABILITY_TOPIC = "intelbras/alarm/availability"; COMMAND_TOPIC = "intelbras/alarm/command"; BASE_TOPIC = "intelbras/alarm"
def _normalize_isecnet_password(password: str | None, length: int) -> str | None:
    if not password:
        return password
    if length and len(password) < length and password.isdigit():
        return password.zfill(length)
    return password

ALARM_PASS_ISECNET = _normalize_isecnet_password(ALARM_PASS, PASSWORD_LENGTH)

alarm_client = AlarmClient(host=ALARM_IP, port=ALARM_PORT) if ALARM_PROTOCOL == "legacy" else None
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
shutdown_event = threading.Event(); alarm_lock = threading.Lock()

# --- Almacén Central de Estados ---
zone_states = {str(i): "Desconocido" for i in range(1, ZONE_COUNT + 1)}

# --- Estado ISECNet (AMT 4010) ---
isecnet_server = None
isecnet_loop = None
isecnet_thread = None
isecnet_connection_id = None

# --- Funciones de MQTT ---
def publish_zone_states():
    for zone_id, state in zone_states.items():
        mqtt_client.publish(f"{BASE_TOPIC}/zone_{zone_id}", state, retain=True)
    logging.info(f"Estados de zona publicados a MQTT: {zone_states}")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        logging.info("Conectado a MQTT y suscrito.")
        client.subscribe(COMMAND_TOPIC)
        client.publish(AVAILABILITY_TOPIC, "online", retain=True)
        # --- INICIO: Publicar estado inicial de nuevos sensores ---
        client.publish(f"{BASE_TOPIC}/ac_power", "on", retain=True)
        client.publish(f"{BASE_TOPIC}/system_battery", "off", retain=True)
        client.publish(f"{BASE_TOPIC}/tamper", "off", retain=True)
        client.publish(f"{BASE_TOPIC}/panic", "off", retain=True)
        publish_zone_states()
        # --- FIN: Publicar estado inicial ---
    else:
        logging.error(f"Fallo al conectar a MQTT: {reason_code}")

def on_message(client, userdata, msg):
    command = msg.payload.decode()
    logging.info(f"Comando MQTT recibido: '{command}'")
    with alarm_lock:
        if ALARM_PROTOCOL == "legacy":
            if not connect_and_auth_alarm():
                logging.error("Fallo de auth, comando no ejecutado.")
                return
        else:
            if not ensure_isecnet_connected():
                logging.error("No hay conexión ISECNet activa, comando no ejecutado.")
                return
        try:
            if command == "ARM_AWAY":
                if ALARM_PROTOCOL == "legacy":
                    alarm_client.arm_system(0)
                else:
                    _send_isecnet_command(ActivationCommand.arm_all(ALARM_PASS_ISECNET))
            elif command == "DISARM":
                if ALARM_PROTOCOL == "legacy":
                    alarm_client.disarm_system(0)
                else:
                    _send_isecnet_command(DeactivationCommand.disarm_all(ALARM_PASS_ISECNET))
            elif command == "PANIC":
                logging.info("¡Activando pánico audible desde Home Assistant!")
                if ALARM_PROTOCOL == "legacy":
                    alarm_client.panic(1) # El tipo 1 suele ser pánico audible
                else:
                    _send_isecnet_command(SirenCommand.turn_on_siren(ALARM_PASS_ISECNET))
                    threading.Timer(30.0, lambda: _send_isecnet_command(SirenCommand.turn_off_siren(ALARM_PASS_ISECNET))).start()
        except (CommunicationError, AuthError) as e: logging.error(f"Error de comunicación en comando: {e}")

# --- Funciones de la Alarma ---
def ensure_isecnet_connected():
    return isecnet_connection_id is not None

def _run_isecnet_server():
    global isecnet_loop
    asyncio.set_event_loop(isecnet_loop)
    isecnet_loop.run_until_complete(isecnet_server.start())
    isecnet_loop.run_forever()

def start_isecnet_server():
    global isecnet_server, isecnet_loop, isecnet_thread
    if isecnet_server:
        return
    config = AMTServerConfig(host="0.0.0.0", port=ALARM_PORT, auto_ack_heartbeat=True, auto_ack_connection=True)
    isecnet_server = AMTServer(config)

    @isecnet_server.on_connect
    async def _on_connect(conn):
        global isecnet_connection_id
        isecnet_connection_id = conn.id
        logging.info(f"Central AMT conectada (ISECNet): {conn.id}")
        # Poll status immediately after connect (in a separate thread to avoid event loop deadlock)
        threading.Thread(target=_poll_isecnet_once, daemon=True).start()

    @isecnet_server.on_disconnect
    async def _on_disconnect(conn):
        global isecnet_connection_id
        if isecnet_connection_id == conn.id:
            isecnet_connection_id = None
        logging.warning(f"Central AMT desconectada (ISECNet): {conn.id}")

    @isecnet_server.on_frame
    async def _on_frame(conn, frame):
        if not frame.is_heartbeat:
            logging.debug(f"Frame ISECNet recibido: cmd=0x{frame.command:02X} data={frame.content.hex()}")

    isecnet_loop = asyncio.new_event_loop()
    isecnet_thread = threading.Thread(target=_run_isecnet_server, daemon=True)
    isecnet_thread.start()

def stop_isecnet_server():
    global isecnet_server, isecnet_loop
    if not isecnet_server or not isecnet_loop:
        return
    fut = asyncio.run_coroutine_threadsafe(isecnet_server.stop(), isecnet_loop)
    try:
        fut.result(timeout=5)
    except Exception:
        pass
    isecnet_loop.call_soon_threadsafe(isecnet_loop.stop)
    isecnet_server = None
    isecnet_loop = None

def _send_isecnet_command(command_obj):
    if not isecnet_server or not isecnet_loop:
        raise CommunicationError("ISECNet server not running")
    if not isecnet_connection_id:
        raise CommunicationError("No ISECNet connection available")
    future = asyncio.run_coroutine_threadsafe(
        isecnet_server.send_command(
            isecnet_connection_id,
            command_obj.build_net_frame(),
            wait_response=True,
        ),
        isecnet_loop,
    )
    return future.result(timeout=10)

def connect_and_auth_alarm():
    for attempt in range(1, 4):
        try:
            alarm_client.connect()
            alarm_client.auth(ALARM_PASS)
            return True
        except (CommunicationError, AuthError) as e:
            logging.error(f"Fallo de conexión/auth (intento {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(1)
    return False

def _map_battery_status_to_percentage(status: str) -> int:
    return {"full": 100, "middle": 75, "low": 25, "dead": 0}.get(status, 0)

def _battery_percentage_from_isecnet(status: CentralStatus) -> int:
    if status.problems.battery_absent or status.problems.battery_short:
        return 0
    if status.problems.low_battery:
        return 25
    return 100

def _model_name_from_isecnet(model_code: int) -> str:
    if model_code == 0x41:
        return "AMT-4010"
    if model_code == 0x1E:
        return "AMT-2018"
    return f"0x{model_code:02X}"

def _publish_isecnet_status(status: CentralStatus):
    mqtt_client.publish(f"{BASE_TOPIC}/model", _model_name_from_isecnet(status.model), retain=True)
    mqtt_client.publish(f"{BASE_TOPIC}/version", status.firmware_version or "Desconocido", retain=True)
    battery_level = _battery_percentage_from_isecnet(status)
    mqtt_client.publish(f"{BASE_TOPIC}/battery_percentage", battery_level, retain=True)
    tamper_state = "on" if (status.zones.tamper_zones or status.problems.keyboard_tamper) else "off"
    mqtt_client.publish(f"{BASE_TOPIC}/tamper", tamper_state, retain=True)
    ac_power_state = "off" if status.problems.ac_failure else "on"
    mqtt_client.publish(f"{BASE_TOPIC}/ac_power", ac_power_state, retain=True)
    system_battery_state = "on" if (status.problems.low_battery or status.problems.battery_absent or status.problems.battery_short) else "off"
    mqtt_client.publish(f"{BASE_TOPIC}/system_battery", system_battery_state, retain=True)
    if status.triggered:
        mqtt_client.publish(f"{BASE_TOPIC}/state", "Disparada", retain=True)
    elif status.armed:
        mqtt_client.publish(f"{BASE_TOPIC}/state", "Armada", retain=True)
    else:
        mqtt_client.publish(f"{BASE_TOPIC}/state", "Desarmada", retain=True)

def _poll_isecnet_once():
    if not ensure_isecnet_connected():
        logging.warning("Sondeo omitido, no hay conexión ISECNet.")
        return
    try:
        logging.info("Sondeando estado de la central (ISECNet)...")
        response = _send_isecnet_command(StatusRequestCommand(ALARM_PASS_ISECNET))
        if response:
            if response.is_error:
                logging.warning(f"ISECNet error: {response.message} (0x{response.code:02X})")
                return
            raw_content = response.raw_frame.content if response.raw_frame else b""
            logging.info(f"Raw Content: {raw_content!r}")
            if raw_content:
                logging.debug(f"ISECNet status raw content len={len(raw_content)}")
            status_payload = b""
            if raw_content and raw_content[0] == 0xFE and len(raw_content) > 1:
                # ACK seguido de datos
                status_payload = raw_content[1:]
            else:
                status_payload = raw_content or response.data

            status = None
            if len(status_payload) == 54:
                status = CentralStatus.try_parse(status_payload)
            elif len(status_payload) == 43:
                partial = PartialCentralStatus.try_parse(status_payload)
                if partial:
                    # Promove parcial para um "status" mínimo
                    status = CentralStatus(
                        model=partial.model,
                        firmware_version=partial.firmware_version,
                        armed=partial.armed,
                        triggered=partial.triggered,
                        siren_on=partial.siren_on,
                        has_problem=partial.has_problem,
                        central_datetime=partial.central_datetime,
                        zones=partial.zones,
                        partitions=partial.partitions,
                        pgm=partial.pgm,
                        problems=partial.problems,
                        raw_data=partial.raw_data,
                    )

            if status:
                _publish_isecnet_status(status)
                for zone_id in range(1, ZONE_COUNT + 1):
                    zone_key = str(zone_id)
                    if zone_id in status.zones.violated_zones:
                        zone_states[zone_key] = "Disparada"
                    elif zone_id in status.zones.open_zones:
                        zone_states[zone_key] = "Abierta"
                    else:
                        if zone_states.get(zone_key) != "Disparada":
                            zone_states[zone_key] = "Cerrada"
                publish_zone_states()
            else:
                logging.warning("Respuesta ISECNet sin datos suficientes para status.")
        else:
            logging.warning("Respuesta ISECNet vacía.")
    except Exception as e:
        logging.warning(f"Error durante sondeo ISECNet: {e}.")

def status_polling_thread():
    logging.info(f"Iniciando sondeo cada {POLLING_INTERVAL_MINUTES} minutos.")
    while not shutdown_event.is_set():
        with alarm_lock:
            if ALARM_PROTOCOL == "legacy":
                if not connect_and_auth_alarm():
                    logging.warning("Sondeo omitido, no se pudo autenticar.")
                else:
                    try:
                        logging.info("Sondeando estado de la central...")
                        logging.info(status)
                        status = alarm_client.status()
                        mqtt_client.publish(f"{BASE_TOPIC}/model", status.get("model", "Desconocido"), retain=True)
                        mqtt_client.publish(f"{BASE_TOPIC}/version", status.get("version", "Desconocido"), retain=True)
                        legacy_state = status.get("status", "unknown")
                        if legacy_state == "armed_away" or legacy_state == "partial_armed":
                            mqtt_client.publish(f"{BASE_TOPIC}/state", "Armada", retain=True)
                        elif legacy_state == "disarmed":
                            mqtt_client.publish(f"{BASE_TOPIC}/state", "Desarmada", retain=True)
                        battery_level = _map_battery_status_to_percentage(status.get("batteryStatus"))
                        mqtt_client.publish(f"{BASE_TOPIC}/battery_percentage", battery_level, retain=True)
                        tamper_state = "on" if status.get("tamper", False) else "off"
                        mqtt_client.publish(f"{BASE_TOPIC}/tamper", tamper_state, retain=True)
                        logging.info(f"Publicados estados generales: Batería={battery_level}%, Tamper={tamper_state}")
                        if 'zones' in status and isinstance(status['zones'], dict):
                            for zone_id, new_state_str in status['zones'].items():
                                if int(zone_id) <= ZONE_COUNT:
                                    if zone_states.get(zone_id) != "Disparada":
                                        zone_states[zone_id] = "Abierta" if new_state_str == "open" else "Cerrada"
                        publish_zone_states()
                    except (CommunicationError, AuthError) as e: logging.warning(f"Error durante sondeo: {e}.")
            else:
                _poll_isecnet_once()
        shutdown_event.wait(POLLING_INTERVAL_MINUTES * 60)
    logging.info("Hilo de sondeo terminado.")

def process_receptorip_output(proc):
    for line in iter(proc.stdout.readline, ''):
        line = line.strip()
        if not line: continue
        logging.info(f"Evento (receptorip): {line}")
        publish_required = False
        with alarm_lock:
            if "Ativacao remota app" in line: mqtt_client.publish(f"{BASE_TOPIC}/state", "Armada", retain=True)
            elif "Desativacao remota app" in line:
                mqtt_client.publish(f"{BASE_TOPIC}/state", "Desarmada", retain=True)
                for zone_id in zone_states: zone_states[zone_id] = "Cerrada"
                publish_required = True
            elif "Panico" in line:
                logging.info(f"¡Evento de pánico detectado: {line}!")
                mqtt_client.publish(f"{BASE_TOPIC}/panic", "on", retain=False)
                threading.Timer(30.0, lambda: mqtt_client.publish(f"{BASE_TOPIC}/panic", "off", retain=False)).start()
            # --- INICIO: Lógica para nuevos sensores de estado ---
            elif "Falta de energia AC" in line:
                mqtt_client.publish(f"{BASE_TOPIC}/ac_power", "off", retain=True)
            elif "Retorno de energia AC" in line:
                mqtt_client.publish(f"{BASE_TOPIC}/ac_power", "on", retain=True)
            elif "Bateria do sistema baixa" in line:
                mqtt_client.publish(f"{BASE_TOPIC}/system_battery", "on", retain=True)
            elif "Recuperacao bateria do sistema baixa" in line:
                mqtt_client.publish(f"{BASE_TOPIC}/system_battery", "off", retain=True)
            # --- FIN: Lógica para nuevos sensores ---
            elif "Disparo de zona" in line:
                try:
                    zone_id = line.split()[-1]
                    if int(zone_id) <= ZONE_COUNT:
                        zone_states[zone_id] = "Disparada"
                        mqtt_client.publish(f"{BASE_TOPIC}/state", "Disparada", retain=True)
                        logging.info(f"Panel de alarma puesto en estado 'Disparada' debido a zona {zone_id}")
                        publish_required = True
                except: logging.warning(f"No se pudo extraer ID de zona de: {line}")
            elif "Restauracao de zona" in line:
                try:
                    zone_id = line.split()[-1]
                    if int(zone_id) <= ZONE_COUNT:
                        zone_states[zone_id] = "Cerrada"
                        publish_required = True
                except: logging.warning(f"No se pudo extraer ID de zona de: {line}")
        if publish_required:
            with alarm_lock:
                publish_zone_states()
    logging.warning("Proceso 'receptorip' terminado.")

def handle_shutdown(signum, frame):
    logging.info("Cerrando addon..."); shutdown_event.set()
    mqtt_client.publish(AVAILABILITY_TOPIC, "offline", retain=True); time.sleep(1)
    mqtt_client.loop_stop()
    if alarm_client:
        alarm_client.close()
    if ALARM_PROTOCOL != "legacy":
        stop_isecnet_server()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_shutdown); signal.signal(signal.SIGINT, handle_shutdown)
    if ALARM_PROTOCOL == "legacy":
        if not all([ALARM_IP, ALARM_PASS, MQTT_BROKER]):
            logging.error("Faltan variables críticas.")
            sys.exit(1)
    else:
        if not all([ALARM_PASS, MQTT_BROKER]):
            logging.error("Faltan variables críticas.")
            sys.exit(1)
        if not ALARM_PASS.isdigit() or len(ALARM_PASS) < 4 or len(ALARM_PASS) > 6:
            logging.error("La contraseña ISECNet debe tener entre 4 y 6 dígitos.")
            sys.exit(1)
    mqtt_client.on_connect = on_connect; mqtt_client.on_message = on_message
    mqtt_client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
    if MQTT_USER: mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    try: mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e: logging.error(f"Fallo al conectar a MQTT: {e}"); sys.exit(1)
    mqtt_client.loop_start()
    if ALARM_PROTOCOL != "legacy":
        start_isecnet_server()
    threading.Thread(target=status_polling_thread, daemon=True).start()
    if ALARM_PROTOCOL == "legacy":
        try:
            logging.info("Iniciando 'receptorip'...")
            proc = subprocess.Popen(["/alarme-intelbras/receptorip", "/alarme-intelbras/config.cfg"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            threading.Thread(target=process_receptorip_output, args=(proc,), daemon=True).start()
        except FileNotFoundError: logging.error("No se encontró 'receptorip'."); sys.exit(1)
    logging.info("Addon en funcionamiento. Esperando eventos..."); shutdown_event.wait()
