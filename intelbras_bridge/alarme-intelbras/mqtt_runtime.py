import logging


class MQTTRuntime:
    def __init__(
        self,
        mqtt_client,
        base_topic,
        command_topic,
        availability_topic,
        zone_states,
        alarm_lock,
        protocol_handler_getter,
    ):
        self.mqtt_client = mqtt_client
        self.base_topic = base_topic
        self.command_topic = command_topic
        self.availability_topic = availability_topic
        self.zone_states = zone_states
        self.alarm_lock = alarm_lock
        self.protocol_handler_getter = protocol_handler_getter

    def configure_client(self):
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.will_set(self.availability_topic, "offline", retain=True)

    def publish_zone_states(self):
        for zone_id, state in self.zone_states.items():
            self.mqtt_client.publish(f"{self.base_topic}/zone_{zone_id}", state, retain=True)
        logging.info(f"Estados de zona publicados a MQTT: {self.zone_states}")

    def publish_triggered_zones_state(self):
        triggered = self._current_triggered_zone_ids()
        self.mqtt_client.publish(
            f"{self.base_topic}/triggered_zones",
            ",".join(triggered) if triggered else "Ninguna",
            retain=True,
        )

    def publish_offline(self):
        self.mqtt_client.publish(self.availability_topic, "offline", retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logging.info("Conectado a MQTT y suscrito.")
            client.subscribe(self.command_topic)
            client.publish(self.availability_topic, "online", retain=True)
            client.publish(f"{self.base_topic}/ac_power", "on", retain=True)
            client.publish(f"{self.base_topic}/system_battery", "off", retain=True)
            client.publish(f"{self.base_topic}/tamper", "off", retain=True)
            client.publish(f"{self.base_topic}/panic", "off", retain=True)
            client.publish(f"{self.base_topic}/triggered_zones", "Ninguna", retain=True)
            client.publish(f"{self.base_topic}/partition_a_state", "OFF", retain=True)
            client.publish(f"{self.base_topic}/partition_b_state", "OFF", retain=True)
            client.publish(f"{self.base_topic}/partition_c_state", "OFF", retain=True)
            client.publish(f"{self.base_topic}/partition_d_state", "OFF", retain=True)
            self.publish_zone_states()
        else:
            logging.error(f"Fallo al conectar a MQTT: {reason_code}")

    def on_message(self, client, userdata, msg):
        command = msg.payload.decode(errors="ignore").strip()
        logging.info(f"Comando MQTT recibido: '{command}'")
        if not command:
            logging.warning("Comando MQTT vacío, ignorado.")
            return
        with self.alarm_lock:
            protocol_handler = self.protocol_handler_getter()
            if protocol_handler is None:
                logging.error("Handler de protocolo no inicializado.")
                return
            protocol_handler.handle_command(command)

    def _current_triggered_zone_ids(self):
        return sorted(
            [zone_id for zone_id, state in self.zone_states.items() if state == "Disparada"],
            key=int,
        )
