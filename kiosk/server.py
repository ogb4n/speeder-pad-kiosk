#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import home
import notion
from upstream import UpstreamError

WWW = Path(__file__).resolve().parent / "www"
MOONRAKER = "http://127.0.0.1:7125"
PORT = 8090
# Identifiants validés avant d'entrer dans une URL d'API.
TASK_PATH = re.compile(r"/api/tasks/([0-9a-fA-F-]{32,36})")
HOME_PATH = re.compile(r"/api/home/([a-z_]+\.[a-z0-9_]+)")
HOME_LIGHT_PATH = re.compile(r"/api/home/([a-z_]+\.[a-z0-9_]+)/light")


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fail(self, error: UpstreamError) -> None:
        # Les erreurs partent aussi dans server.log : la page, elle, n'en affiche qu'un résumé.
        self.log_message("%s : %s", error.status, error)
        self.send_json(error.status, {"error": str(error)})

    def read_json_body(self) -> dict:
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 4096)
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        try:
            if path == "/api/tasks":
                self.send_json(200, {"tasks": notion.TASKS.get(), "actions": notion.actions()})
            elif path == "/api/home":
                self.send_json(200, {"tiles": home.TILES.get()})
            elif path == "/api/shopping":
                self.send_json(200, {"items": notion.SHOPPING.get()})
            else:
                super().do_GET()
        except UpstreamError as error:
            self.fail(error)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        home_match = HOME_PATH.fullmatch(path)
        light_match = HOME_LIGHT_PATH.fullmatch(path)
        try:
            if path == "/api/klipperscreen":
                self.switch_to_klipperscreen()
            elif path == "/api/tasks":
                notion.create_task(str(self.read_json_body().get("title", "")))
                self.send_json(201, {})
            elif path == "/api/shopping":
                notion.add_shopping_item(str(self.read_json_body().get("name", "")))
                self.send_json(201, {})
            elif home_match:
                home.activate(home_match.group(1))
                self.send_json(200, {})
            elif light_match:
                body = self.read_json_body()
                home.set_light(light_match.group(1), body.get("rgb"), body.get("kelvin"), body.get("brightness"))
                self.send_json(200, {})
            else:
                self.send_error(404)
        except UpstreamError as error:
            self.fail(error)

    def do_PATCH(self) -> None:
        match = TASK_PATH.fullmatch(self.path.split("?")[0])
        if match is None:
            self.send_error(404)
            return
        try:
            notion.change_state(match.group(1), str(self.read_json_body().get("state", "")))
            self.send_json(200, {})
        except UpstreamError as error:
            self.fail(error)

    def switch_to_klipperscreen(self) -> None:
        # Passer par Moonraker (service déjà déclaré dans moonraker.asvc) évite tout CORS et tout sudo.
        # Systemd arrête kiosk.service (Conflicts=) pendant cet appel : la réponse peut ne jamais partir.
        request = urllib.request.Request(
            f"{MOONRAKER}/machine/services/start?service=KlipperScreen", method="POST"
        )
        try:
            urllib.request.urlopen(request, timeout=30).read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise UpstreamError(502, f"Moonraker : {error}") from error
        self.send_response(204)
        self.end_headers()


def main() -> None:
    handler = partial(Handler, directory=str(WWW))
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()


if __name__ == "__main__":
    main()
