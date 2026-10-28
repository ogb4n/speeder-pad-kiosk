from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from upstream import TtlCache, UpstreamError, read_env_value, read_json_config, request_json

HERE = Path(__file__).resolve().parent
# Hors de www/ : le jeton ne doit jamais être servi à la page. Fichier en mode 600.
ENV_FILE = HERE / "notion.env"
CONFIG_FILE = HERE / "notion.json"

API = "https://api.notion.com/v1"
# Version antérieure aux « data sources » : l'interrogation par database_id reste valable pour une base à une seule source.
VERSION = "2022-06-28"
TIMEZONE = ZoneInfo("Europe/Paris")
CACHE_SECONDS = 15
MAX_TITLE = 120


def read_config() -> dict:
    return read_json_config(CONFIG_FILE)


def notion_request(method: str, path: str, body: dict | None = None) -> dict:
    token = read_env_value(ENV_FILE, "NOTION_TOKEN")
    if token is None:
        raise UpstreamError(503, "jeton Notion absent")
    request = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": VERSION,
            "Content-Type": "application/json",
        },
    )
    return request_json(request, "Notion")


def today() -> str:
    return datetime.now(TIMEZONE).date().isoformat()


def build_filter(config: dict, day: str) -> dict:
    names = config["properties"]
    state_type = config.get("state_type", "status")
    state = names["state"]
    conditions = [{"property": state, state_type: {"does_not_equal": s}} for s in config["done_states"]]
    # Base sans date d'échéance (tâches ménagères) : tout ce qui n'est pas terminé est « du jour ».
    if names.get("due"):
        # Échéance atteinte ou dépassée, ou état « actif » même sans date ; jamais une tâche terminée.
        due_or_active = [{"property": names["due"], "date": {"on_or_before": day}}]
        due_or_active += [{"property": state, state_type: {"equals": s}} for s in config.get("active_states", [])]
        conditions.append({"or": due_or_active})
    return {"and": conditions}


def page_emoji(page: dict) -> str | None:
    # Seules les icônes emoji sont renvoyées : les icônes Notion natives et les images n'ont pas d'équivalent texte.
    icon = page.get("icon")
    return icon["emoji"] if icon and icon.get("type") == "emoji" else None


def parse_task(page: dict, config: dict) -> dict:
    names = config["properties"]
    properties = page["properties"]
    title = "".join(part["plain_text"] for part in properties[names["title"]]["title"]).strip()
    state = (properties[names["state"]][config.get("state_type", "status")] or {}).get("name", "")
    priority = None
    if names.get("priority"):
        priority = (properties[names["priority"]]["select"] or {}).get("name")
    return {
        "id": page["id"],
        "emoji": page_emoji(page),
        "title": title,
        "priority": priority,
        "state": config.get("state_labels", {}).get(state, state),
    }


def fetch_tasks() -> list[dict]:
    config = read_config()
    due = config["properties"].get("due")
    sort = {"property": due, "direction": "ascending"} if due else {"timestamp": "created_time", "direction": "ascending"}
    try:
        data = notion_request(
            "POST",
            f"/databases/{config['database_id']}/query",
            {"filter": build_filter(config, today()), "sorts": [sort], "page_size": 30},
        )
        parsed = (parse_task(page, config) for page in data["results"])
        # Une ligne sans titre (la ligne vide d'une base neuve) n'est pas une tâche.
        tasks = [task for task in parsed if task["title"]]
    except KeyError as error:
        raise UpstreamError(500, f"propriété Notion introuvable : {error}") from error
    # Tri stable : l'ordre de Notion (échéance ou création) départage les ex æquo.
    priorities = {name: i for i, name in enumerate(config.get("priority_order", []))}
    states = {name: i for i, name in enumerate(config.get("state_order", []))}
    tasks.sort(key=lambda task: (priorities.get(task["priority"], len(priorities)), states.get(task["state"], len(states))))
    return tasks


TASKS: TtlCache[list[dict]] = TtlCache(lambda: fetch_tasks(), CACHE_SECONDS)


def actions() -> list[dict]:
    return read_config().get("actions", [])


def create_task(title: str) -> None:
    title = title.strip()
    if not 0 < len(title) <= MAX_TITLE:
        raise UpstreamError(400, f"titre de 1 à {MAX_TITLE} caractères")
    config = read_config()
    names = config["properties"]
    properties = {names["title"]: {"title": [{"text": {"content": title}}]}}
    if names.get("due"):
        properties[names["due"]] = {"date": {"start": today()}}
    notion_request("POST", "/pages", {"parent": {"database_id": config["database_id"]}, "properties": properties})
    TASKS.invalidate()


def fetch_shopping() -> list[dict]:
    shopping = read_config()["shopping"]
    names = shopping["properties"]
    data = notion_request(
        "POST",
        f"/databases/{shopping['database_id']}/query",
        {"sorts": [{"timestamp": "created_time", "direction": "ascending"}], "page_size": 100},
    )
    items = []
    try:
        for page in data["results"]:
            properties = page["properties"]
            name = "".join(part["plain_text"] for part in properties[names["name"]]["title"]).strip()
            if not name:  # la ligne vide d'une base neuve n'est pas un article
                continue
            quantity = properties[names["quantity"]]["number"] if names.get("quantity") else None
            unit = (properties[names["unit"]]["select"] or {}).get("name") if names.get("unit") else None
            items.append({"id": page["id"], "emoji": page_emoji(page), "name": name, "quantity": quantity, "unit": unit})
    except KeyError as error:
        raise UpstreamError(500, f"propriété Notion introuvable : {error}") from error
    return items


SHOPPING: TtlCache[list[dict]] = TtlCache(lambda: fetch_shopping(), CACHE_SECONDS)


def add_shopping_item(name: str) -> None:
    name = name.strip()
    if not 0 < len(name) <= MAX_TITLE:
        raise UpstreamError(400, f"nom de 1 à {MAX_TITLE} caractères")
    shopping = read_config()["shopping"]
    notion_request(
        "POST",
        "/pages",
        {
            "parent": {"database_id": shopping["database_id"]},
            "properties": {shopping["properties"]["name"]: {"title": [{"text": {"content": name}}]}},
        },
    )
    SHOPPING.invalidate()


def change_state(page_id: str, state: str) -> None:
    config = read_config()
    # Liste blanche : seuls les états déclarés dans notion.json sont acceptés.
    if state not in {action["state"] for action in config.get("actions", [])}:
        raise UpstreamError(400, "état non autorisé")
    notion_request(
        "PATCH",
        f"/pages/{page_id}",
        {"properties": {config["properties"]["state"]: {config.get("state_type", "status"): {"name": state}}}},
    )
    TASKS.invalidate()
