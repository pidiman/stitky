"""Brother-only Fajny Print gateway, independent of the standalone firmware."""
import re
from urllib.parse import urlsplit
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import text_sensor, esp32
from esphome.const import CONF_ID
DEPENDENCIES = ["esp32", "wifi", "ota"]
AUTO_LOAD = ["json", "text_sensor"]
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

CONFIG_SCHEMA = cv.All(cv.Schema({
    cv.GenerateID(): cv.declare_id(FajnyBrother),
    cv.Required("api_url"): endpoint,
    cv.Required("agent_token"): token,
    cv.Required("printer_host"): host,
    cv.Optional("max_payload", default=131072): cv.int_range(min=16384,max=131072),
    cv.Optional("status"): text_sensor.text_sensor_schema(),
}).extend(cv.COMPONENT_SCHEMA), cv.only_on_esp32)

async def to_code(config):
    cg.add_define("USE_OTA_STATE_LISTENER")
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    for key in ("api_url", "agent_token", "printer_host", "max_payload"):
        cg.add(getattr(var,"set_"+key)(config[key]))
    if "status" in config:
        sensor = await text_sensor.new_text_sensor(config["status"])
        cg.add(var.set_status_sensor(sensor))
    esp32.add_idf_sdkconfig_option("CONFIG_MBEDTLS_CERTIFICATE_BUNDLE", True)
    esp32.add_idf_sdkconfig_option("CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL", True)
