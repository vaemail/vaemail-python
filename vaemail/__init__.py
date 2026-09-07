"""SDK Python de VaEmail.

Aucune dépendance : `urllib` suffit, et un paquet destiné à être installé par un
agent doit pouvoir s'installer sans rien tirer derrière lui. C'est le même parti
pris que le paquet npm.

    from vaemail import VaEmail

    client = VaEmail(api_key="...")
    client.send({"to": "x@exemple.fr", "subject": "Bonjour", "html": "<p>Bonjour</p>"})
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

__all__ = ["VaEmail", "VaEmailError", "DEFAULT_BASE_URL"]
__version__ = "1.0.0"

DEFAULT_BASE_URL = "https://app.vaemail.fr"


class VaEmailError(Exception):
    """Erreur rendue par l'API.

    Porte ce qu'un appelant doit savoir pour décider : le code, l'action
    corrective proposée, et si le même appel peut aboutir plus tard. Une
    exception qui ne dit que « erreur 422 » oblige à lire la documentation ;
    celle-ci porte la suite.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "UNKNOWN",
        status: int | None = None,
        resolution: dict[str, Any] | None = None,
        retryable: bool = False,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.resolution = resolution or {}
        self.retryable = retryable
        self.body = body

    def for_agent(self) -> str:
        """Le motif, l'action corrective et s'il faut réessayer, en clair."""
        lignes = [f"{self.code}: {self}"]

        action = self.resolution.get("action")
        if action:
            endpoint = self.resolution.get("endpoint")
            lignes.append(
                f"Action corrective : {action}" + (f" ({endpoint})" if endpoint else "")
            )

        lignes.append(
            "Le même appel peut aboutir plus tard."
            if self.retryable
            else "Réessayer à l'identique ne changera rien."
        )

        return "\n".join(lignes)


class VaEmail:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        opener: Any = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Injectable pour les tests : on ne veut pas d'appel réseau dans une
        # suite de tests, et on ne veut pas non plus d'une dépendance de test.
        self._opener = opener or urllib.request.urlopen

    # -- transport ---------------------------------------------------------

    def _call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        url = self.base_url + path

        propres = {k: v for k, v in (query or {}).items() if v not in (None, "")}
        if propres:
            url += "?" + urllib.parse.urlencode(propres)

        entetes = {"Accept": "application/json"}
        if self.api_key:
            entetes["api-key"] = self.api_key
        if idempotency_key:
            entetes["Idempotency-Key"] = idempotency_key

        donnees = None
        if body is not None:
            donnees = json.dumps(body).encode("utf-8")
            entetes["Content-Type"] = "application/json"

        requete = urllib.request.Request(url, data=donnees, headers=entetes, method=method)

        try:
            with self._opener(requete, timeout=self.timeout) as reponse:
                brut = reponse.read().decode("utf-8") or "{}"
                charge = json.loads(brut)
        except urllib.error.HTTPError as erreur:
            brut = erreur.read().decode("utf-8") or "{}"
            try:
                charge = json.loads(brut)
            except json.JSONDecodeError:
                charge = {}
            raise self._erreur(charge, erreur.code) from None

        # Une réponse 200 peut porter une erreur applicative : on la lève aussi,
        # sinon l'appelant croit avoir réussi.
        if isinstance(charge, dict) and charge.get("error"):
            raise self._erreur(charge, 200)

        return charge

    @staticmethod
    def _erreur(charge: Any, status: int) -> VaEmailError:
        details = charge.get("error", {}) if isinstance(charge, dict) else {}

        return VaEmailError(
            details.get("message") or f"Erreur HTTP {status}.",
            code=details.get("code", "UNKNOWN"),
            status=status,
            resolution=details.get("resolution"),
            retryable=bool(details.get("retryable")),
            body=charge,
        )

    # -- API ---------------------------------------------------------------

    def capabilities(self) -> Any:
        return self._call("GET", "/api/v1/capabilities")

    def health(self) -> Any:
        return self._call("GET", "/api/v1/health")

    def send(self, message: dict[str, Any], idempotency_key: str | None = None) -> Any:
        """Envoie un message. `idempotency_key` rend l'appel rejouable sans doublon 24 h."""
        return self._call(
            "POST", "/api/v1/transactional/send", body=message, idempotency_key=idempotency_key
        )

    def validate(self, message: dict[str, Any]) -> Any:
        """Essai à blanc : mêmes contrôles que l'envoi, rien ne part."""
        return self._call("POST", "/api/v1/messages/validate", body=message)

    def get_message(self, message_id: str | int) -> Any:
        return self._call("GET", f"/api/v1/messages/{urllib.parse.quote(str(message_id))}")

    def list_messages(self, **filters: Any) -> Any:
        return self._call("GET", "/api/v1/messages", query=filters)

    def list_domains(self) -> Any:
        return self._call("GET", "/api/v1/domains")

    def add_domain(
        self,
        domain: str,
        *,
        selector: str | None = None,
        dkim_tokens: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        """Déclare un domaine d'envoi.

        `dkim_tokens` sont les trois valeurs données par SES à la création de
        l'identité de domaine. Sans elles, la partie DKIM du guide DNS rendu est
        un marqueur et le domaine ne peut pas être terminé sans intervention.
        """
        corps: dict[str, Any] = {"domain": domain}
        if selector:
            corps["dkim_selector"] = selector
        if dkim_tokens:
            corps["dkim_tokens"] = list(dkim_tokens)

        return self._call("POST", "/api/v1/domains", body=corps, idempotency_key=idempotency_key)

    def verify_domain(self, domain: str, selector: str | None = None) -> Any:
        corps: dict[str, Any] = {"domain": domain}
        if selector:
            corps["dkim_selector"] = selector

        return self._call("POST", "/api/v1/domains/verify", body=corps)

    def dns_records(self, domain: str) -> Any:
        return self._call("GET", f"/api/v1/domains/{urllib.parse.quote(domain)}/dns")

    def diagnose_deliverability(self, domain: str) -> Any:
        return self._call("GET", "/api/v1/deliverability/diagnose", query={"domain": domain})

    def list_suppressions(self, **filters: Any) -> Any:
        return self._call("GET", "/api/v1/suppressions", query=filters)

    def usage(self) -> Any:
        return self._call("GET", "/api/v1/usage")

    def audit_logs(self, **filters: Any) -> Any:
        return self._call("GET", "/api/v1/audit-logs", query=filters)
