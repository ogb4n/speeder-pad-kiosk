from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from upstream import TtlCache, UpstreamError, read_env_value, read_json_config, request_json

HERE = Path(__file__).resolve().parent
# Hors de www/ : le jeton ne doit jamais être servi à la page. Fichier en mode 600.
ENV_FILE = HERE / "ha.env"
CONFIG_FILE = HERE / "ha.json"

CACHE_SECONDS = 3
COLOR_MODES = {"hs", "rgb", "rgbw", "rgbww", "xy"}
# Domaine de l'entité -> service appelé par un appui. Tout autre domaine est refusé.
SERVICES = {
    "light": ("light", "toggle"),
    "switch": ("switch", "toggle"),
    "input_boolean": ("input_boolean", "toggle"),
    "script": ("script", "turn_on"),
    "scene": ("scene", "turn_on"),
}


def read_config() -> dict:
    return read_json_config(CONFIG_FILE)


def ha_request(method: str, path: str, body: dict | None = None) -> dict | list:
    token = read_env_value(ENV_FILE, "HA_TOKEN")
    if token is None:
        raise UpstreamError(503, "jeton Home Assistant absent")
    request = urllib.request.Request(
        read_config()["url"] + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    return request_json(request, "Home Assistant")


def light_info(attributes: dict) -> dict:
    modes = set(attributes.get("supported_color_modes") or [])
    brightness = attributes.get("brightness")
    return {
        "colors": bool(modes & COLOR_MODES),
        "temp": "color_temp" in modes,
        "rgb": attributes.get("rgb_color"),
        "brightness": round(brightness / 2.55) if brightness else None,
    }


def fetch_tiles() -> list[dict]:
    config = read_config()
    entities = {entity["entity_id"]: entity for entity in ha_request("GET", "/api/states")}
    tiles = []
    for tile in config["entities"]:
        entity = entities.get(tile["entity_id"])
        tile = {**tile, "state": entity["state"] if entity else "unavailable"}
        if entity and tile["entity_id"].startswith("light."):
            tile["light"] = light_info(entity["attributes"])
        tiles.append(tile)
    return tiles


TILES: TtlCache[list[dict]] = TtlCache(lambda: fetch_tiles(), CACHE_SECONDS)


def require_allowed(entity_id: str) -> None:
    # Liste blanche : seules les entités déclarées dans ha.json sont commandables depuis la page.
    if entity_id not in {tile["entity_id"] for tile in read_config()["entities"]}:
        raise UpstreamError(404, "entité non autorisée")


def activate(entity_id: str) -> None:
    require_allowed(entity_id)
    domain = entity_id.split(".")[0]
    if domain not in SERVICES:
        raise UpstreamError(400, "type d'entité non pris en charge")
    service_domain, service = SERVICES[domain]
    ha_request("POST", f"/api/services/{service_domain}/{service}", {"entity_id": entity_id})
    TILES.invalidate()


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def set_light(entity_id: str, rgb: object = None, kelvin: object = None, brightness: object = None) -> None:
    require_allowed(entity_id)
    if not entity_id.startswith("light."):
        raise UpstreamError(400, "cette entité n'est pas une lumière")
    data: dict = {"entity_id": entity_id}
    if rgb is not None:
        if not (isinstance(rgb, list) and len(rgb) == 3 and all(is_int(c) and 0 <= c <= 255 for c in rgb)):
            raise UpstreamError(400, "couleur invalide")
        data["rgb_color"] = rgb
    if kelvin is not None:
        if not (is_int(kelvin) and 1500 <= kelvin <= 10000):
            raise UpstreamError(400, "température de couleur invalide")
        data["color_temp_kelvin"] = kelvin
    if brightness is not None:
        if not (is_int(brightness) and 1 <= brightness <= 100):
            raise UpstreamError(400, "luminosité invalide")
        data["brightness_pct"] = brightness
    if rgb is not None and kelvin is not None:
        raise UpstreamError(400, "une seule couleur à la fois")
    if len(data) == 1:
        raise UpstreamError(400, "aucun réglage demandé")
    # light.turn_on allume aussi la lumière si elle est éteinte, ce qui est voulu : on règle pour s'en servir.
    ha_request("POST", "/api/services/light/turn_on", data)
    TILES.invalidate()
