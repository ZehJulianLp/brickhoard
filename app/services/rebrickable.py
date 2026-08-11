from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class RebrickableAPIError(Exception):
    """A safe, user-facing Rebrickable API failure."""


class RebrickableService:
    BASE_URL = "https://rebrickable.com/api/v3"

    def __init__(
        self,
        api_key: str,
        user_token: str | None = None,
        *,
        timeout: tuple[float, float] = (3.05, 12),
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.user_token = user_token.strip() if user_token else None
        self.timeout = timeout
        self.session = session or requests.Session()

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise RebrickableAPIError("Es ist kein Rebrickable-API-Key konfiguriert.")
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            response = self.session.get(
                url,
                headers={"Authorization": f"key {self.api_key}"},
                params=params or {},
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            logger.warning("Rebrickable-Anfrage an %s wegen Zeitüberschreitung fehlgeschlagen", path)
            raise RebrickableAPIError(
                "Die Verbindung zu Rebrickable hat zu lange gedauert."
            ) from exc
        except requests.ConnectionError as exc:
            logger.warning("Rebrickable ist für %s nicht erreichbar", path)
            raise RebrickableAPIError(
                "Rebrickable ist momentan nicht erreichbar. Bitte versuche es später erneut."
            ) from exc
        except requests.RequestException as exc:
            logger.warning("Rebrickable-Anfrage an %s fehlgeschlagen: %s", path, type(exc).__name__)
            raise RebrickableAPIError(
                "Die Rebrickable-Anfrage konnte nicht ausgeführt werden."
            ) from exc

        return self._parse_response(response, path)

    def _parse_response(self, response: requests.Response, path: str) -> Any:
        if response.status_code in {401, 403}:
            logger.warning("Rebrickable lehnte Zugangsdaten für %s ab", path)
            raise RebrickableAPIError(
                "Der Rebrickable-API-Key oder User Token wurde abgelehnt."
            )
        if response.status_code == 404:
            raise RebrickableAPIError("Die angeforderten Rebrickable-Daten wurden nicht gefunden.")
        if response.status_code == 429:
            logger.warning("Rebrickable-Rate-Limit bei %s erreicht", path)
            raise RebrickableAPIError(
                "Das Rebrickable-Anfragelimit ist erreicht. Bitte warte einen Moment."
            )
        if response.status_code >= 500:
            logger.warning("Rebrickable-Serverfehler %s bei %s", response.status_code, path)
            raise RebrickableAPIError(
                "Rebrickable ist momentan nicht verfügbar. Bitte versuche es später erneut."
            )
        if not response.ok:
            logger.warning("Rebrickable-HTTP-Fehler %s bei %s", response.status_code, path)
            raise RebrickableAPIError("Die Rebrickable-Anfrage wurde abgelehnt.")
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("Ungültige Rebrickable-Antwort bei %s", path)
            raise RebrickableAPIError("Rebrickable hat eine ungültige Antwort geliefert.") from exc

    def generate_user_token(self, username: str, password: str) -> str:
        """Generate a private user token without retaining the account password."""
        if not self.api_key:
            raise RebrickableAPIError("Es ist kein Rebrickable-API-Key konfiguriert.")
        path = "users/_token/"
        try:
            response = self.session.post(
                f"{self.BASE_URL}/{path}",
                headers={"Authorization": f"key {self.api_key}"},
                data={"username": username, "password": password},
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            logger.warning("Rebrickable-Token-Anfrage wegen Zeitüberschreitung fehlgeschlagen")
            raise RebrickableAPIError(
                "Die Verbindung zu Rebrickable hat zu lange gedauert."
            ) from exc
        except requests.ConnectionError as exc:
            logger.warning("Rebrickable ist für die Token-Anfrage nicht erreichbar")
            raise RebrickableAPIError(
                "Rebrickable ist momentan nicht erreichbar. Bitte versuche es später erneut."
            ) from exc
        except requests.RequestException as exc:
            logger.warning("Rebrickable-Token-Anfrage fehlgeschlagen: %s", type(exc).__name__)
            raise RebrickableAPIError(
                "Der Rebrickable User Token konnte nicht erzeugt werden."
            ) from exc

        if response.status_code == 400:
            raise RebrickableAPIError(
                "Rebrickable hat Benutzername/E-Mail oder Passwort abgelehnt."
            )
        payload = self._parse_response(response, path)
        token = payload.get("user_token") if isinstance(payload, dict) else None
        if not token:
            raise RebrickableAPIError("Rebrickable hat keinen User Token geliefert.")
        return str(token)

    def _user_path(self, suffix: str) -> str:
        if not self.user_token:
            raise RebrickableAPIError("Es ist kein Rebrickable User Token konfiguriert.")
        token = quote(self.user_token, safe="")
        return f"users/{token}/{suffix.lstrip('/')}"

    def get_user_set_lists(self, *, fetch_all: bool = True) -> dict[str, Any]:
        path = self._user_path("setlists/")
        if not fetch_all:
            return self._request(path, {"page_size": 100})

        page = 1
        results: list[dict[str, Any]] = []
        total = 0
        while True:
            payload = self._request(path, {"page": page, "page_size": 1000})
            if not isinstance(payload, dict):
                raise RebrickableAPIError("Rebrickable hat eine unerwartete Antwort geliefert.")
            total = int(payload.get("count", len(results)))
            results.extend(payload.get("results") or [])
            if not payload.get("next"):
                break
            page += 1
        return {"count": total, "results": results, "next": None, "previous": None}

    def get_user_set_list(self, list_id: int) -> dict[str, Any]:
        return self._request(self._user_path(f"setlists/{list_id}/"))

    def get_sets_in_list(
        self, list_id: int, *, page: int = 1, page_size: int = 24
    ) -> dict[str, Any]:
        return self._request(
            self._user_path(f"setlists/{list_id}/sets/"),
            {"page": page, "page_size": min(max(page_size, 1), 1000)},
        )

    def search_user_sets(
        self, query: str, *, page: int = 1, page_size: int = 24
    ) -> dict[str, Any]:
        return self._request(
            self._user_path("sets/"),
            {
                "search": query,
                "page": max(page, 1),
                "page_size": min(max(page_size, 1), 1000),
                "ordering": "set__name",
            },
        )

    def get_set_details(self, set_number: str) -> dict[str, Any]:
        number = quote(set_number, safe="-")
        return self._request(f"lego/sets/{number}/")

    def get_set_parts(self, set_number: str) -> list[dict[str, Any]]:
        number = quote(set_number, safe="-")
        path = f"lego/sets/{number}/parts/"
        page = 1
        parts: list[dict[str, Any]] = []
        while True:
            payload = self._request(
                path,
                {"page": page, "page_size": 1000, "inc_part_details": 1},
            )
            if not isinstance(payload, dict):
                raise RebrickableAPIError("Rebrickable hat eine unerwartete Antwort geliefert.")
            parts.extend(payload.get("results") or [])
            if not payload.get("next"):
                return parts
            page += 1

    def get_theme_details(self, theme_id: int) -> dict[str, Any]:
        return self._request(f"lego/themes/{theme_id}/")

    def test_connection(self) -> dict[str, Any]:
        return self._request(self._user_path("profile/"))
