import asyncio
import logging
import threading

from client import CommunicationError
from isecnet.protocol.commands import (
    ActivationCommand,
    DeactivationCommand,
    SirenCommand,
    StatusRequestCommand,
)
from isecnet.protocol.commands.status import CentralStatus, PartialCentralStatus
from isecnet.server import AMTServer, AMTServerConfig


class ISECNetProtocolHandler:
    uses_receptorip = False

    def __init__(
        self,
        alarm_pass,
        alarm_port,
        mqtt_client,
        base_topic,
        zone_states,
        zone_count,
        alarm_lock,
    ):
        self.alarm_pass = alarm_pass
        self.alarm_port = alarm_port
        self.mqtt_client = mqtt_client
        self.base_topic = base_topic
        self.zone_states = zone_states
        self.zone_count = zone_count
        self.alarm_lock = alarm_lock

        self.server = None
        self.loop = None
        self.thread = None
        self.connection_id = None

        self._command_actions = {
            "ARM_AWAY": lambda: self._send_command(ActivationCommand.arm_all(self.alarm_pass)),
            "ARM_HOME": lambda: self._send_command(ActivationCommand.arm_partition_a(self.alarm_pass)),
            "ARM_NIGHT": lambda: self._send_command(ActivationCommand.arm_partition_b(self.alarm_pass)),
            "ARM_VACATION": lambda: self._send_command(ActivationCommand.arm_partition_c(self.alarm_pass)),
            "ARM_CUSTOM_BYPASS": lambda: self._send_command(ActivationCommand.arm_partition_d(self.alarm_pass)),
            "ARM_PART_A": lambda: self._send_command(ActivationCommand.arm_partition_a(self.alarm_pass)),
            "ARM_PART_B": lambda: self._send_command(ActivationCommand.arm_partition_b(self.alarm_pass)),
            "ARM_PART_C": lambda: self._send_command(ActivationCommand.arm_partition_c(self.alarm_pass)),
            "ARM_PART_D": lambda: self._send_command(ActivationCommand.arm_partition_d(self.alarm_pass)),
            "DISARM_PART_A": lambda: self._send_command(DeactivationCommand.disarm_partition_a(self.alarm_pass)),
            "DISARM_PART_B": lambda: self._send_command(DeactivationCommand.disarm_partition_b(self.alarm_pass)),
            "DISARM_PART_C": lambda: self._send_command(DeactivationCommand.disarm_partition_c(self.alarm_pass)),
            "DISARM_PART_D": lambda: self._send_command(DeactivationCommand.disarm_partition_d(self.alarm_pass)),
            "DISARM": lambda: self._send_command(DeactivationCommand.disarm_all(self.alarm_pass)),
        }
        self._command_aliases = {
            "ARM_PARTITION_A": "ARM_PART_A",
            "ARM_PARTITION_B": "ARM_PART_B",
            "ARM_PARTITION_C": "ARM_PART_C",
            "ARM_PARTITION_D": "ARM_PART_D",
            "DISARM_PARTITION_A": "DISARM_PART_A",
            "DISARM_PARTITION_B": "DISARM_PART_B",
            "DISARM_PARTITION_C": "DISARM_PART_C",
            "DISARM_PARTITION_D": "DISARM_PART_D",
        }

    def validate_startup(self, alarm_ip, mqtt_broker):
        if not all([self.alarm_pass, mqtt_broker]):
            return False, "Faltan variables críticas."
        if not self.alarm_pass.isdigit() or len(self.alarm_pass) < 4 or len(self.alarm_pass) > 6:
            return False, "La contraseña ISECNet debe tener entre 4 y 6 dígitos."
        return True, ""

    def start(self):
        if self.server is not None:
            return

        config = AMTServerConfig(host="0.0.0.0", port=self.alarm_port, auto_ack_heartbeat=True, auto_ack_connection=True)
        self.server = AMTServer(config)

        @self.server.on_connect
        async def _on_connect(conn):
            self.connection_id = conn.id
            logging.info(f"Central AMT conectada (ISECNet): {conn.id}")
            threading.Thread(target=self._poll_status_after_connect, daemon=True).start()

        @self.server.on_disconnect
        async def _on_disconnect(conn):
            if self.connection_id == conn.id:
                self.connection_id = None
            logging.warning(f"Central AMT desconectada (ISECNet): {conn.id}")

        @self.server.on_frame
        async def _on_frame(conn, frame):
            if not frame.is_heartbeat:
                logging.debug(f"Frame ISECNet recibido: cmd=0x{frame.command:02X} data={frame.content.hex()}")

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def poll_status(self):
        if not self._ensure_connected():
            logging.warning("Sondeo omitido, no hay conexión ISECNet.")
            return

        try:
            logging.info("Sondeando estado de la central (ISECNet)...")
            response = self._send_command(StatusRequestCommand(self.alarm_pass))
            if not response:
                logging.warning("Respuesta ISECNet vacía.")
                return

            if response.is_error:
                logging.warning(f"ISECNet error: {response.message} (0x{response.code:02X})")
                return

            raw_content = response.raw_frame.content if response.raw_frame else b""
            if raw_content:
                logging.debug(f"ISECNet status raw content len={len(raw_content)}")

            if raw_content and raw_content[0] == 0xFE and len(raw_content) > 1:
                status_payload = raw_content[1:]
            else:
                status_payload = raw_content or response.data

            status = self._parse_status(status_payload)
            if not status:
                logging.warning("Respuesta ISECNet sin datos suficientes para status.")
                return

            self._publish_status(status)
            for zone_id in range(1, self.zone_count + 1):
                zone_key = str(zone_id)
                if zone_id in status.zones.violated_zones:
                    self.zone_states[zone_key] = "Disparada"
                elif zone_id in status.zones.open_zones:
                    self.zone_states[zone_key] = "Abierta"
                elif self.zone_states.get(zone_key) != "Disparada":
                    self.zone_states[zone_key] = "Cerrada"
        except Exception as exc:
            logging.warning(f"Error durante sondeo ISECNet: {exc}.")

    def handle_command(self, command):
        command_key = self._normalize_command(command)
        if not self._ensure_connected():
            logging.error("No hay conexión ISECNet activa, comando no ejecutado.")
            return

        try:
            if command_key == "PANIC":
                logging.info("¡Activando pánico audible desde Home Assistant!")
                self._send_command(SirenCommand.turn_on_siren(self.alarm_pass))
                self._schedule_siren_off(30.0)
                return

            action = self._command_actions.get(command_key)
            if action is None:
                logging.warning(f"Comando no reconocido: {command}")
                return

            action()
            logging.info(f"Comando ejecutado por ISECNet: {command_key}")
        except CommunicationError as exc:
            logging.error(f"Error de comunicación en comando: {exc}")

    def shutdown(self):
        if not self.server or not self.loop:
            return

        fut = asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass

        self.loop.call_soon_threadsafe(self.loop.stop)
        self.server = None
        self.loop = None
        self.thread = None
        self.connection_id = None

    def _run_server(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.server.start())
        self.loop.run_forever()

    def _poll_status_after_connect(self):
        with self.alarm_lock:
            self.poll_status()

    def _ensure_connected(self):
        return self.connection_id is not None

    def _send_command(self, command_obj):
        if not self.server or not self.loop:
            raise CommunicationError("ISECNet server not running")
        if not self.connection_id:
            raise CommunicationError("No ISECNet connection available")

        future = asyncio.run_coroutine_threadsafe(
            self.server.send_command(
                self.connection_id,
                command_obj.build_net_frame(),
                wait_response=True,
            ),
            self.loop,
        )
        return future.result(timeout=10)

    def _schedule_siren_off(self, delay_seconds=30.0):
        def _safe_turn_off():
            with self.alarm_lock:
                try:
                    if not self._ensure_connected():
                        logging.warning("No hay conexión ISECNet para apagar la sirena automáticamente.")
                        return
                    self._send_command(SirenCommand.turn_off_siren(self.alarm_pass))
                except Exception as exc:
                    logging.warning(f"No se pudo apagar la sirena automáticamente: {exc}")

        threading.Timer(delay_seconds, _safe_turn_off).start()

    def _normalize_command(self, command):
        key = str(command).strip().upper().replace("-", "_").replace(" ", "_")
        return self._command_aliases.get(key, key)

    def _publish_status(self, status):
        self.mqtt_client.publish(f"{self.base_topic}/model", self._model_name(status.model), retain=True)
        self.mqtt_client.publish(f"{self.base_topic}/version", status.firmware_version or "Desconocido", retain=True)

        battery_level = self._battery_percentage(status)
        self.mqtt_client.publish(f"{self.base_topic}/battery_percentage", battery_level, retain=True)

        tamper_state = "on" if (status.zones.tamper_zones or status.problems.keyboard_tamper) else "off"
        self.mqtt_client.publish(f"{self.base_topic}/tamper", tamper_state, retain=True)

        ac_power_state = "off" if status.problems.ac_failure else "on"
        self.mqtt_client.publish(f"{self.base_topic}/ac_power", ac_power_state, retain=True)

        system_battery_state = "on" if (
            status.problems.low_battery or status.problems.battery_absent or status.problems.battery_short
        ) else "off"
        self.mqtt_client.publish(f"{self.base_topic}/system_battery", system_battery_state, retain=True)

        alarm_active = status.armed
        alarm_triggered_now = bool(status.siren_on or status.zones.violated_zones)
        alarm_memory = bool(status.triggered)
        self.mqtt_client.publish(f"{self.base_topic}/alarm_memory", "on" if alarm_memory else "off", retain=True)

        violated_list = sorted(status.zones.violated_zones)
        triggered_zones = ",".join(str(zone) for zone in violated_list) if violated_list else "Ninguna"
        self.mqtt_client.publish(f"{self.base_topic}/triggered_zones", triggered_zones, retain=True)

        if not status.armed and not status.siren_on:
            partition_state = "OFF"
        elif status.siren_on:
            partition_state = "ON"
        elif status.partitions.partitions_enabled:
            partition_state = None
        else:
            partition_state = "ON" if status.armed else "OFF"

        if partition_state is None:
            self.mqtt_client.publish(
                f"{self.base_topic}/partition_a_state",
                "ON" if status.partitions.partition_a_armed else "OFF",
                retain=True,
            )
            self.mqtt_client.publish(
                f"{self.base_topic}/partition_b_state",
                "ON" if status.partitions.partition_b_armed else "OFF",
                retain=True,
            )
            self.mqtt_client.publish(
                f"{self.base_topic}/partition_c_state",
                "ON" if status.partitions.partition_c_armed else "OFF",
                retain=True,
            )
            self.mqtt_client.publish(
                f"{self.base_topic}/partition_d_state",
                "ON" if status.partitions.partition_d_armed else "OFF",
                retain=True,
            )
        else:
            self.mqtt_client.publish(f"{self.base_topic}/partition_a_state", partition_state, retain=True)
            self.mqtt_client.publish(f"{self.base_topic}/partition_b_state", partition_state, retain=True)
            self.mqtt_client.publish(f"{self.base_topic}/partition_c_state", partition_state, retain=True)
            self.mqtt_client.publish(f"{self.base_topic}/partition_d_state", partition_state, retain=True)

        if alarm_active and alarm_triggered_now:
            self.mqtt_client.publish(f"{self.base_topic}/state", "Disparada", retain=True)
        elif status.armed:
            if status.partitions.partitions_enabled:
                if status.partitions.all_armed:
                    self.mqtt_client.publish(f"{self.base_topic}/state", "Armada", retain=True)
                else:
                    self.mqtt_client.publish(f"{self.base_topic}/state", "Armada Parcial", retain=True)
            else:
                self.mqtt_client.publish(f"{self.base_topic}/state", "Armada", retain=True)
        else:
            self.mqtt_client.publish(f"{self.base_topic}/state", "Desarmada", retain=True)

    @staticmethod
    def _model_name(model_code):
        if model_code == 0x41:
            return "AMT-4010"
        if model_code == 0x1E:
            return "AMT-2018"
        return f"0x{model_code:02X}"

    @staticmethod
    def _battery_percentage(status):
        if status.problems.battery_absent or status.problems.battery_short:
            return 0
        if status.problems.low_battery:
            return 25
        return 100

    @staticmethod
    def _parse_status(payload):
        if len(payload) == 54:
            return CentralStatus.try_parse(payload)
        if len(payload) == 43:
            partial = PartialCentralStatus.try_parse(payload)
            if partial:
                return CentralStatus(
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
        return None
