import logging
import subprocess
import threading
import time

from client import AuthError, CommunicationError


class AMT8000ProtocolHandler:
    def __init__(
        self,
        alarm_client,
        alarm_pass,
        mqtt_client,
        base_topic,
        zone_states,
        alarm_lock,
        publish_zone_states,
        publish_triggered_zones_state,
    ):
        self.alarm_client = alarm_client
        self.alarm_pass = alarm_pass
        self.mqtt_client = mqtt_client
        self.base_topic = base_topic
        self.zone_states = zone_states
        self.alarm_lock = alarm_lock
        self.publish_zone_states = publish_zone_states
        self.publish_triggered_zones_state = publish_triggered_zones_state
        self.receptorip_proc = None

        self._command_actions = {
            "ARM_AWAY": lambda: self.alarm_client.arm_system(0),
            "DISARM": lambda: self.alarm_client.disarm_system(0),
            "PANIC": lambda: self.alarm_client.panic(1),
        }

    def validate_startup(self, alarm_ip, mqtt_broker):
        if not all([alarm_ip, self.alarm_pass, mqtt_broker]):
            return False, "Faltan variables críticas."
        return True, ""

    def start(self):
        try:
            logging.info("Iniciando 'receptorip'...")
            self.receptorip_proc = subprocess.Popen(
                ["/alarme-intelbras/receptorip", "/alarme-intelbras/config.cfg"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            threading.Thread(target=self._process_receptorip_output, daemon=True).start()
        except FileNotFoundError as exc:
            raise RuntimeError("No se encontró 'receptorip'.") from exc

    def connect_and_auth_alarm(self):
        for attempt in range(1, 4):
            try:
                self.alarm_client.connect()
                self.alarm_client.auth(self.alarm_pass)
                return True
            except (CommunicationError, AuthError) as exc:
                logging.error(f"Fallo de conexión/auth (intento {attempt}/3): {exc}")
                if attempt < 3:
                    time.sleep(1)
        return False

    def handle_command(self, command):
        if not self.connect_and_auth_alarm():
            logging.error("Fallo de auth, comando no ejecutado.")
            return

        if command in {
            "ARM_HOME",
            "ARM_NIGHT",
            "ARM_VACATION",
            "ARM_CUSTOM_BYPASS",
            "ARM_PART_A",
            "ARM_PART_B",
            "ARM_PART_C",
            "ARM_PART_D",
            "DISARM_PART_A",
            "DISARM_PART_B",
            "DISARM_PART_C",
            "DISARM_PART_D",
        }:
            logging.warning(f"{command} no está soportado en protocolo amt8000.")
            return

        action = self._command_actions.get(command)
        if action is None:
            logging.warning(f"Comando no reconocido: {command}")
            return

        try:
            if command == "PANIC":
                logging.info("¡Activando pánico audible desde Home Assistant!")
            action()
        except (CommunicationError, AuthError) as exc:
            logging.error(f"Error de comunicación en comando: {exc}")

    def poll_status(self):
        if not self.connect_and_auth_alarm():
            logging.warning("Sondeo omitido, no se pudo autenticar.")
            return

        try:
            logging.info("Sondeando estado de la central...")
            status = self.alarm_client.status()
            self.mqtt_client.publish(f"{self.base_topic}/model", status.get("model", "Desconocido"), retain=True)
            self.mqtt_client.publish(f"{self.base_topic}/version", status.get("version", "Desconocido"), retain=True)

            amt8000_state = status.get("status", "unknown")
            state_map = {
                "armed_away": "Armada",
                "partial_armed": "Armada Parcial",
                "disarmed": "Desarmada",
            }
            mapped_state = state_map.get(amt8000_state)
            if mapped_state:
                self.mqtt_client.publish(f"{self.base_topic}/state", mapped_state, retain=True)

            triggered = "Desconocido" if status.get("zonesFiring") else "Ninguna"
            self.mqtt_client.publish(f"{self.base_topic}/triggered_zones", triggered, retain=True)

            battery_level = self._map_battery_status_to_percentage(status.get("batteryStatus"))
            self.mqtt_client.publish(f"{self.base_topic}/battery_percentage", battery_level, retain=True)

            tamper_state = "on" if status.get("tamper", False) else "off"
            self.mqtt_client.publish(f"{self.base_topic}/tamper", tamper_state, retain=True)
            logging.info(f"Publicados estados generales: Batería={battery_level}%, Tamper={tamper_state}")

            zones = status.get("zones")
            if isinstance(zones, dict):
                for zone_id, new_state_str in zones.items():
                    if zone_id in self.zone_states and self.zone_states.get(zone_id) != "Disparada":
                        self.zone_states[zone_id] = "Abierta" if new_state_str == "open" else "Cerrada"
        except (CommunicationError, AuthError) as exc:
            logging.warning(f"Error durante sondeo: {exc}.")
        except Exception:
            logging.exception("Error inesperado durante sondeo amt8000.")

    def shutdown(self):
        if self.receptorip_proc and self.receptorip_proc.poll() is None:
            self.receptorip_proc.terminate()
        self.alarm_client.close()

    def _process_receptorip_output(self):
        if not self.receptorip_proc or self.receptorip_proc.stdout is None:
            return

        for line in iter(self.receptorip_proc.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue

            logging.info(f"Evento (receptorip): {line}")
            publish_required = False

            with self.alarm_lock:
                if "Ativacao remota app" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/state", "Armada", retain=True)
                elif "Desativacao remota app" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/state", "Desarmada", retain=True)
                    for zone_id in self.zone_states:
                        self.zone_states[zone_id] = "Cerrada"
                    self.publish_triggered_zones_state()
                    publish_required = True
                elif "Panico" in line:
                    logging.info(f"¡Evento de pánico detectado: {line}!")
                    self.mqtt_client.publish(f"{self.base_topic}/panic", "on", retain=False)
                    threading.Timer(
                        30.0,
                        lambda: self.mqtt_client.publish(f"{self.base_topic}/panic", "off", retain=False),
                    ).start()
                elif "Falta de energia AC" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/ac_power", "off", retain=True)
                elif "Retorno de energia AC" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/ac_power", "on", retain=True)
                elif "Bateria do sistema baixa" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/system_battery", "on", retain=True)
                elif "Recuperacao bateria do sistema baixa" in line:
                    self.mqtt_client.publish(f"{self.base_topic}/system_battery", "off", retain=True)
                elif "Disparo de zona" in line:
                    try:
                        zone_id = line.split()[-1]
                        if zone_id in self.zone_states:
                            self.zone_states[zone_id] = "Disparada"
                            self.mqtt_client.publish(f"{self.base_topic}/state", "Disparada", retain=True)
                            self.publish_triggered_zones_state()
                            logging.info(f"Panel de alarma puesto en estado 'Disparada' debido a zona {zone_id}")
                            publish_required = True
                    except (ValueError, IndexError):
                        logging.warning(f"No se pudo extraer ID de zona de: {line}")
                elif "Restauracao de zona" in line:
                    try:
                        zone_id = line.split()[-1]
                        if zone_id in self.zone_states:
                            self.zone_states[zone_id] = "Cerrada"
                            self.publish_triggered_zones_state()
                            publish_required = True
                    except (ValueError, IndexError):
                        logging.warning(f"No se pudo extraer ID de zona de: {line}")

            if publish_required:
                with self.alarm_lock:
                    self.publish_zone_states()

        logging.warning("Proceso 'receptorip' terminado.")

    @staticmethod
    def _map_battery_status_to_percentage(status):
        return {"full": 100, "middle": 75, "low": 25, "dead": 0}.get(status, 0)
