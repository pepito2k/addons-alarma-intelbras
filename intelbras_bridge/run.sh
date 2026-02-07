#!/usr/bin/with-contenv bash

# --- FUNCIONES Y TRAPS (TRAMPAS) ---
log() { echo "=> $1"; }
config() {
    local key="$1"
    local default="${2-}"
    local value=""
    if [[ -f /data/options.json ]]; then
        value="$(jq -r --arg key "$key" 'if has($key) and .[$key] != null then .[$key] else "" end' /data/options.json 2>/dev/null || true)"
    fi
    if [[ -z "$value" && -n "${default-}" ]]; then
        echo "$default"
    else
        echo "$value"
    fi
}
cleanup() {
    log "Encerrando..."; pkill -P $$
    local BROKER_IP=$(config 'mqtt_broker'); local BROKER_PORT=$(config 'mqtt_port'); local MQTT_USER=$(config 'mqtt_user'); local MQTT_PASS=$(config 'mqtt_password')
    local MQTT_CLEANUP_OPTS=(-h "$BROKER_IP" -p "$BROKER_PORT"); [[ -n "$MQTT_USER" ]] && MQTT_CLEANUP_OPTS+=(-u "$MQTT_USER" -P "$MQTT_PASS")
    mosquitto_pub "${MQTT_CLEANUP_OPTS[@]}" -r -t "intelbras/alarm/availability" -m "offline" || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# --- LECTURA DE CONFIGURACIÓN ---
log "Iniciando Intelbras MQTT Bridge Add-on (v7.5 - Corrección Device Class)"
export ALARM_IP=$(config 'alarm_ip'); export ALARM_PORT=$(config 'alarm_port'); export ALARM_PASS=$(config 'alarm_password')
export ALARM_PROTOCOL=$(config 'alarm_protocol' 'isecnet')
if [[ "${ALARM_PROTOCOL}" == "legacy" || "${ALARM_PROTOCOL}" == "amt800" ]]; then
    log "El valor '${ALARM_PROTOCOL}' está deprecado; usando 'amt8000'."
    export ALARM_PROTOCOL="amt8000"
fi
export MQTT_BROKER=$(config 'mqtt_broker'); export MQTT_PORT=$(config 'mqtt_port'); export MQTT_USER=$(config 'mqtt_user'); export MQTT_PASS=$(config 'mqtt_password')
export POLLING_INTERVAL_MINUTES=$(config 'polling_interval_minutes' 5)
export ZONE_COUNT=$(config 'zone_count' 0)
export ZONE_RANGE=$(config 'zone_range')
export ZONE_NAMES=$(config 'zone_names' '{}')
export PASSWORD_LENGTH=$(config 'password_length')
MQTT_OPTS=(-h "$MQTT_BROKER" -p "$MQTT_PORT"); [[ -n "$MQTT_USER" ]] && MQTT_OPTS+=(-u "$MQTT_USER" -P "$MQTT_PASS")
AVAILABILITY_TOPIC="intelbras/alarm/availability"; DEVICE_ID="intelbras_alarm"; DISCOVERY_PREFIX="homeassistant"
if [[ -z "${ZONE_RANGE}" && "${ZONE_COUNT}" -gt 0 ]]; then
    export ZONE_RANGE="1-${ZONE_COUNT}"
fi
log "Configuración cargada. Rango de zonas: ${ZONE_RANGE:-vacío}."
if ! echo "${ZONE_NAMES}" | jq -e . >/dev/null 2>&1; then
    log "zone_names inválido, se ignorará (debe ser JSON objeto, ej: {\"17\":\"Puerta Principal\"})"
    export ZONE_NAMES="{}"
fi

# --- FUNCIONES DE DISCOVERY (formato legible) ---
publish_device_info() {
    local model_name="AMT-8000"
    if [[ "${ALARM_PROTOCOL}" != "amt8000" ]]; then
        model_name="AMT-4010"
    fi
    echo "\"device\":{\"identifiers\":[\"${DEVICE_ID}\"],\"name\":\"Alarma Intelbras\",\"model\":\"${model_name}\",\"manufacturer\":\"Intelbras\"}"
}
publish_binary_sensor_discovery() {
    local name=$1; local uid=$2; local device_class=$3; local icon=${4:-}
    local payload='{'; payload+="\"name\":\"${name}\",\"state_topic\":\"intelbras/alarm/${uid}\",\"unique_id\":\"${uid}\",\"device_class\":\"${device_class}\","; payload+="\"payload_on\":\"on\",\"payload_off\":\"off\",\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; [[ -n "$icon" ]] && payload+="\"icon\":\"${icon}\","; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/binary_sensor/${DEVICE_ID}/${uid}/config" -m "${payload}"
}
publish_text_sensor_discovery() {
    local name=$1; local uid=$2; local icon=$3
    local state_topic="intelbras/alarm/${uid}"
    local payload='{'; payload+="\"name\":\"${name}\",\"state_topic\":\"${state_topic}\",\"unique_id\":\"${uid}\",\"icon\":\"${icon}\","; payload+="\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/sensor/${DEVICE_ID}/${uid}/config" -m "${payload}"
}
publish_numeric_sensor_discovery() {
    local name=$1; local uid=$2; local device_class=$3; local unit=$4; local icon=$5
    local state_topic="intelbras/alarm/${uid}"
    local payload='{'; payload+="\"name\":\"${name}\",\"state_topic\":\"${state_topic}\",\"unique_id\":\"${uid}\",\"device_class\":\"${device_class}\","; payload+="\"unit_of_measurement\":\"${unit}\",\"icon\":\"${icon}\",\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/sensor/${DEVICE_ID}/${uid}/config" -m "${payload}"
}
publish_alarm_panel_discovery() {
    log "Publicando Painel de Alarme..."; local uid="${DEVICE_ID}_panel"; local command_topic="intelbras/alarm/command"; local state_topic="intelbras/alarm/state"
    local supported_features='["arm_away"]'
    local extra_payload=""
    if [[ "${ALARM_PROTOCOL}" != "amt8000" ]]; then
        supported_features='["arm_away","arm_home","arm_night","arm_vacation","arm_custom_bypass"]'
        extra_payload="\"payload_arm_home\":\"ARM_HOME\",\"payload_arm_night\":\"ARM_NIGHT\",\"payload_arm_vacation\":\"ARM_VACATION\",\"payload_arm_custom_bypass\":\"ARM_CUSTOM_BYPASS\","
    fi
    local payload='{'; payload+="\"name\":\"Painel de Alarma Intelbras\",\"unique_id\":\"${uid}\",\"state_topic\":\"${state_topic}\","; payload+="\"command_topic\":\"${command_topic}\",\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; payload+="\"value_template\":\"{% if value == 'Disparada' %}triggered{% elif value == 'Armada Parcial' %}armed_home{% elif value == 'Armada' %}armed_away{% else %}disarmed{% endif %}\","; payload+="\"payload_disarm\":\"DISARM\",\"payload_arm_away\":\"ARM_AWAY\","; payload+="${extra_payload}"; payload+="\"supported_features\":${supported_features},"; payload+="\"code_arm_required\":false,\"code_disarm_required\":false,"; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/alarm_control_panel/${DEVICE_ID}/config" -m "${payload}"
}
remove_partition_alarm_panel_discovery() {
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/alarm_control_panel/${DEVICE_ID}/${DEVICE_ID}_partition_a/config" -n
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/alarm_control_panel/${DEVICE_ID}/${DEVICE_ID}_partition_b/config" -n
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/alarm_control_panel/${DEVICE_ID}/${DEVICE_ID}_partition_c/config" -n
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/alarm_control_panel/${DEVICE_ID}/${DEVICE_ID}_partition_d/config" -n
}
publish_button_discovery() {
    local name=$1; local uid=$2; local icon=$3; local payload_press=${4:-PANIC}
    local command_topic="intelbras/alarm/command"
    local payload='{'; payload+="\"name\":\"${name}\",\"unique_id\":\"${uid}\",\"command_topic\":\"${command_topic}\","; payload+="\"payload_press\":\"${payload_press}\",\"icon\":\"${icon}\",\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/button/${DEVICE_ID}/${uid}/config" -m "${payload}"
}
publish_partition_switch_discovery() {
    local partition_letter=$1
    local partition_name=$2
    local uid="${DEVICE_ID}_partition_${partition_letter}_switch"
    local state_topic="intelbras/alarm/partition_${partition_letter}_state"
    local command_topic="intelbras/alarm/command"
    local payload='{'; payload+="\"name\":\"Partición ${partition_name}\",\"unique_id\":\"${uid}\",\"state_topic\":\"${state_topic}\",\"command_topic\":\"${command_topic}\","; payload+="\"payload_on\":\"ARM_PART_${partition_name}\",\"payload_off\":\"DISARM_PART_${partition_name}\","; payload+="\"state_on\":\"ON\",\"state_off\":\"OFF\",\"icon\":\"mdi:shield-lock\",\"availability_topic\":\"${AVAILABILITY_TOPIC}\","; payload+="$(publish_device_info)"; payload+='}';
    mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/switch/${DEVICE_ID}/${uid}/config" -m "${payload}"
}

clear_zone_discovery() {
    local i
    for i in $(seq 1 64); do
        mosquitto_pub "${MQTT_OPTS[@]}" -r -t "${DISCOVERY_PREFIX}/sensor/${DEVICE_ID}/zone_${i}/config" -n
    done
}

zone_id_list() {
    local range_text="${ZONE_RANGE}"
    if [[ -z "${range_text}" ]]; then
        return
    fi
    local chunk
    IFS=',' read -ra chunks <<< "${range_text}"
    for chunk in "${chunks[@]}"; do
        chunk="${chunk// /}"
        [[ -z "${chunk}" ]] && continue
        if [[ "${chunk}" == *-* ]]; then
            local start="${chunk%-*}"
            local end="${chunk#*-}"
            if [[ "${start}" =~ ^[0-9]+$ && "${end}" =~ ^[0-9]+$ ]]; then
                if (( end >= start )); then
                    seq "${start}" "${end}"
                else
                    seq "${end}" "${start}"
                fi
            fi
        elif [[ "${chunk}" =~ ^[0-9]+$ ]]; then
            echo "${chunk}"
        fi
    done | awk '!seen[$0]++'
}

zone_name_for_id() {
    local zone_id="$1"
    local custom_name
    custom_name="$(echo "${ZONE_NAMES}" | jq -r --arg zid "${zone_id}" 'if type == "object" then (.[$zid] // empty) else empty end' 2>/dev/null || true)"
    if [[ -n "${custom_name}" ]]; then
        echo "${custom_name}"
    else
        echo "Zona ${zone_id}"
    fi
}

# --- PUBLICACIÓN DE ENTIDADES ---
log "Configurando Home Assistant Discovery..."
remove_partition_alarm_panel_discovery
publish_alarm_panel_discovery
publish_text_sensor_discovery "Estado Alarma" "state" "mdi:shield-lock"
publish_text_sensor_discovery "Modelo Alarma" "model" "mdi:chip"
publish_text_sensor_discovery "Versión Firmware" "version" "mdi:git"
publish_text_sensor_discovery "Zonas Disparadas" "triggered_zones" "mdi:alert-circle"
publish_numeric_sensor_discovery "Batería Alarma" "battery_percentage" "battery" "%" "mdi:battery"
publish_binary_sensor_discovery "Tamper Alarma" "tamper" "tamper"
publish_binary_sensor_discovery "Pánico Silencioso" "panic" "safety"
publish_binary_sensor_discovery "Memoria de Disparo" "alarm_memory" "problem"
publish_button_discovery "Pánico Audible" "panic_button" "mdi:alert-decagram"

# --- INICIO: LÍNEAS CORREGIDAS ---
publish_binary_sensor_discovery "Alimentación AC" "ac_power" "power"
publish_binary_sensor_discovery "Batería del Sistema" "system_battery" "battery"
# --- FIN: LÍNEAS CORREGIDAS ---

log "Publicando sensores de zona de texto individuales..."
clear_zone_discovery
for i in $(zone_id_list); do
    publish_text_sensor_discovery "$(zone_name_for_id "$i")" "zone_$i" "mdi:door"
done

if [[ "${ALARM_PROTOCOL}" != "amt8000" ]]; then
    log "Publicando switches de particiones..."
    publish_partition_switch_discovery "a" "A"
    publish_partition_switch_discovery "b" "B"
    publish_partition_switch_discovery "c" "C"
    publish_partition_switch_discovery "d" "D"

    log "Publicando botones de particiones..."
    publish_button_discovery "Armar Partición A" "arm_part_a" "mdi:shield-lock" "ARM_PART_A"
    publish_button_discovery "Armar Partición B" "arm_part_b" "mdi:shield-lock" "ARM_PART_B"
    publish_button_discovery "Armar Partición C" "arm_part_c" "mdi:shield-lock" "ARM_PART_C"
    publish_button_discovery "Armar Partición D" "arm_part_d" "mdi:shield-lock" "ARM_PART_D"
    publish_button_discovery "Desarmar Partición A" "disarm_part_a" "mdi:shield-off" "DISARM_PART_A"
    publish_button_discovery "Desarmar Partición B" "disarm_part_b" "mdi:shield-off" "DISARM_PART_B"
    publish_button_discovery "Desarmar Partición C" "disarm_part_c" "mdi:shield-off" "DISARM_PART_C"
    publish_button_discovery "Desarmar Partición D" "disarm_part_d" "mdi:shield-off" "DISARM_PART_D"
fi

# --- GENERACIÓN DE CONFIG.CFG ---
if [[ "${ALARM_PROTOCOL}" == "amt8000" ]]; then
log "Generando config.cfg para receptorip..."
cat > /alarme-intelbras/config.cfg <<EOF
[receptorip]
addr = 0.0.0.0
port = ${ALARM_PORT}
centrais = .*
maxconn = 1
caddr = ${ALARM_IP}
cport = ${ALARM_PORT}
senha = ${ALARM_PASS}
tamanho = ${PASSWORD_LENGTH}
folder_dlfoto = .
logfile = receptorip.log
EOF
fi

# --- LANZAMIENTO DEL SCRIPT PRINCIPAL ---
log "Lanzando el script principal de Python (addon_main.py)..."
exec python3 /alarme-intelbras/addon_main.py
