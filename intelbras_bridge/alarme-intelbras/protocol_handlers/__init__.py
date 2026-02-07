from client import Client as AlarmClient

from protocol_handlers.amt8000 import AMT8000ProtocolHandler
from protocol_handlers.isecnet import ISECNetProtocolHandler


def _normalize_isecnet_password(password, length):
    if not password:
        return password
    if length and len(password) < length and password.isdigit():
        return password.zfill(length)
    return password


def create_protocol_handler(
    protocol,
    alarm_ip,
    alarm_port,
    alarm_pass,
    password_length,
    mqtt_client,
    base_topic,
    zone_states,
    zone_count,
    alarm_lock,
    publish_zone_states,
    publish_triggered_zones_state,
):
    normalized = (protocol or "").lower()
    if normalized == "amt8000":
        return AMT8000ProtocolHandler(
            alarm_client=AlarmClient(host=alarm_ip, port=alarm_port),
            alarm_pass=alarm_pass,
            mqtt_client=mqtt_client,
            base_topic=base_topic,
            zone_states=zone_states,
            zone_count=zone_count,
            alarm_lock=alarm_lock,
            publish_zone_states=publish_zone_states,
            publish_triggered_zones_state=publish_triggered_zones_state,
        )

    return ISECNetProtocolHandler(
        alarm_pass=_normalize_isecnet_password(alarm_pass, password_length),
        alarm_port=alarm_port,
        mqtt_client=mqtt_client,
        base_topic=base_topic,
        zone_states=zone_states,
        zone_count=zone_count,
        alarm_lock=alarm_lock,
    )
