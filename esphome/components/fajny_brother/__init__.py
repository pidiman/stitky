"""Fajny Print ESPHome gateway: Brother and optional P15 BLE."""
import re
from urllib.parse import urlsplit
import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import sensor, binary_sensor, text_sensor, esp32, ble_client, esp32_ble, esp32_ble_tracker
from esphome.const import CONF_ID
DEPENDENCIES = ["esp32", "wifi", "ota"]
AUTO_LOAD = ["json", "text_sensor", "sensor", "binary_sensor"]
ns = cg.esphome_ns.namespace("fajny_brother")
FajnyBrother = ns.class_("FajnyBrother", cg.Component)

def endpoint(value):
    value = cv.string_strict(value).rstrip("/")
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.path or p.query or p.fragment:
        raise cv.Invalid("api_url must be an HTTPS origin without a path or credentials")
    return value

def host(value):
    value = cv.string_strict(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", value):
        raise cv.Invalid("printer_host must be a local hostname or IPv4 address, without a port/path")
    return value

def token(value):
    value=cv.string_strict(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}",value):
        raise cv.Invalid("agent_token must be the gateway token from the print application")
    return value

P15_SCHEMA = cv.Schema({
    cv.Required("agent_token"): token,
    cv.Required("ble_client_id"): cv.use_id(ble_client.BLEClient),
    cv.Required("ble_id"): cv.use_id(esp32_ble.ESP32BLE),
    cv.Required("tracker_id"): cv.use_id(esp32_ble_tracker.ESP32BLETracker),
    cv.Optional("status"): text_sensor.text_sensor_schema(),
    cv.Optional("battery"): sensor.sensor_schema(unit_of_measurement="%", accuracy_decimals=0, device_class="battery", state_class="measurement"),
    cv.Optional("printer_available"): binary_sensor.binary_sensor_schema(),
    cv.Optional("printer_status"): text_sensor.text_sensor_schema(),
    cv.Optional("last_error"): text_sensor.text_sensor_schema(),
    cv.Optional("last_check"): text_sensor.text_sensor_schema(),
})

CONFIG_SCHEMA = cv.All(cv.Schema({
    cv.GenerateID(): cv.declare_id(FajnyBrother),
    cv.Required("api_url"): endpoint,
    cv.Required("agent_token"): token,
    cv.Required("printer_host"): host,
    cv.Optional("max_payload", default=131072): cv.int_range(min=16384,max=131072),
    cv.Optional("status"): text_sensor.text_sensor_schema(),
    cv.Optional("p15"): P15_SCHEMA,
}).extend(cv.COMPONENT_SCHEMA), cv.only_on_esp32)

async def to_code(config):
    cg.add_define("USE_OTA_STATE_LISTENER")
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    for key in ("api_url", "agent_token", "printer_host", "max_payload"):
        cg.add(getattr(var,"set_"+key)(config[key]))
    if "status" in config:
        status_entity = await text_sensor.new_text_sensor(config["status"])
        cg.add(var.set_status_sensor(status_entity))
    if "p15" in config:
        conf = config["p15"]
        cg.add_define("USE_FPS_P15")
        cg.add(var.set_p15_token(conf["agent_token"]))
        cg.add(var.set_p15_client(await cg.get_variable(conf["ble_client_id"])))
        cg.add(var.set_p15_ble(await cg.get_variable(conf["ble_id"])))
        cg.add(var.set_p15_tracker(await cg.get_variable(conf["tracker_id"])))
        if "status" in conf:
            status_entity = await text_sensor.new_text_sensor(conf["status"])
            cg.add(var.set_p15_status_sensor(status_entity))
        for key, factory in (("battery", sensor.new_sensor), ("printer_available", binary_sensor.new_binary_sensor),
                             ("printer_status", text_sensor.new_text_sensor), ("last_error", text_sensor.new_text_sensor),
                             ("last_check", text_sensor.new_text_sensor)):
            if key in conf:
                entity = await factory(conf[key])
                cg.add(getattr(var, "set_p15_" + key)(entity))
    esp32.add_idf_sdkconfig_option("CONFIG_MBEDTLS_CERTIFICATE_BUNDLE", True)
    esp32.add_idf_sdkconfig_option("CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL", True)


def final_validate(config):
    if "p15" not in config:
        return config
    full = fv.full_config.get()
    ble = full.get("esp32_ble", {})
    tracker = full.get("esp32_ble_tracker", {})
    if ble.get("enable_on_boot", True) or ble.get("max_connections", 3) != 1:
        raise cv.Invalid("P15 gateway requires esp32_ble enable_on_boot: false and max_connections: 1")
    if tracker.get("scan_parameters", {}).get("continuous", True):
        raise cv.Invalid("P15 gateway requires non-continuous BLE scanning")
    conf = config["p15"]
    if conf["agent_token"] == config["agent_token"]:
        raise cv.Invalid("P15 and Brother require separate agent tokens")
    clients = full.get("ble_client", [])
    selected = next((c for c in clients if c["id"] == conf["ble_client_id"]), None)
    if selected is None or selected.get("auto_connect", True):
        raise cv.Invalid("The P15 BLE client must use auto_connect: false")
    return config

FINAL_VALIDATE_SCHEMA = final_validate
