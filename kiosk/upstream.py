from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Generic, TypeVar

T = TypeVar("T")
TIMEOUT_SECONDS = 15


class UpstreamError(Exception):
    """Erreur d'un service distant, avec le statut HTTP à renvoyer à la page."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def read_env_value(path: Path, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"') or None
    return None


def read_json_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise UpstreamError(500, f"{path.name} absent ou invalide") from error


def request_json(request: urllib.request.Request, service: str) -> dict | list:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("message", "")
        except (ValueError, OSError, AttributeError):
            detail = ""
        raise UpstreamError(502, f"{service} {error.code} {detail}".strip()) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise UpstreamError(502, f"{service} injoignable") from error


class TtlCache(Generic[T]):
    """Valeur recalculée au plus toutes les `ttl` secondes, la précédente servant de repli si le service tombe."""

    def __init__(self, fetch: Callable[[], T], ttl: float) -> None:
        self._fetch = fetch
        self._ttl = ttl
        self._lock = threading.Lock()
        self._value: T | None = None
        self._fetched_at = 0.0

    def get(self) -> T:
        with self._lock:
            fresh = time.monotonic() - self._fetched_at < self._ttl
            if self._value is not None and fresh:
                return self._value
            try:
                self._value = self._fetch()
                self._fetched_at = time.monotonic()
            except UpstreamError:
                # Mieux vaut l'affichage précédent qu'un écran d'erreur sur un afficheur permanent.
                if self._value is None:
                    raise
            return self._value

    def invalidate(self) -> None:
        with self._lock:
            self._fetched_at = 0.0
