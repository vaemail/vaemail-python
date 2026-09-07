"""Ce qui compte est ce qui part sur le réseau : on l'observe avec un faux opener.

Pas de dépendance de test non plus (unittest de la bibliothèque standard), pour
que `python -m unittest` suffise partout.
"""

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vaemail import DEFAULT_BASE_URL, VaEmail, VaEmailError  # noqa: E402


class FausseReponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False


def espion(charge=None, statut=200):
    appels = []

    def opener(requete, timeout=None):
        appels.append(requete)
        corps = json.dumps(charge if charge is not None else {"success": True, "data": {}})
        if statut >= 400:
            raise urllib.error.HTTPError(
                requete.full_url, statut, "erreur", {}, io.BytesIO(corps.encode())
            )
        return FausseReponse(corps.encode())

    return appels, opener


class TestSdk(unittest.TestCase):
    def test_la_cle_part_en_entete_et_la_base_est_la_production(self):
        appels, opener = espion()
        VaEmail(api_key="cle-test", opener=opener).capabilities()

        self.assertEqual(appels[0].full_url, f"{DEFAULT_BASE_URL}/api/v1/capabilities")
        self.assertEqual(appels[0].get_header("Api-key"), "cle-test")

    def test_les_jetons_dkim_sont_transmis(self):
        appels, opener = espion()
        VaEmail(api_key="k", opener=opener).add_domain(
            "news.exemple.fr", dkim_tokens=["aaa111", "bbb222", "ccc333"]
        )

        corps = json.loads(appels[0].data)
        self.assertEqual(corps["dkim_tokens"], ["aaa111", "bbb222", "ccc333"])
        self.assertNotIn("dkim_selector", corps)

    def test_la_cle_d_idempotence_part_en_entete(self):
        appels, opener = espion()
        VaEmail(api_key="k", opener=opener).send({"to": "x@exemple.fr"}, "commande-42")

        self.assertEqual(appels[0].get_header("Idempotency-key"), "commande-42")

    def test_les_filtres_vides_ne_polluent_pas_l_url(self):
        appels, opener = espion()
        VaEmail(api_key="k", opener=opener).list_messages(status="sent", limit=None)

        self.assertIn("status=sent", appels[0].full_url)
        self.assertNotIn("limit", appels[0].full_url)

    def test_une_erreur_dit_quoi_faire_et_si_l_appel_peut_etre_rejoue(self):
        _, opener = espion(
            {
                "error": {
                    "code": "DOMAIN_NOT_VERIFIED",
                    "message": "Domaine non authentifié.",
                    "resolution": {"action": "verify_domain", "endpoint": "/api/v1/domains/verify"},
                    "retryable": False,
                }
            },
            422,
        )

        with self.assertRaises(VaEmailError) as capture:
            VaEmail(api_key="k", opener=opener).send({"to": "x@exemple.fr"})

        erreur = capture.exception
        self.assertEqual(erreur.code, "DOMAIN_NOT_VERIFIED")
        self.assertEqual(erreur.status, 422)
        self.assertFalse(erreur.retryable)
        self.assertIn("verify_domain", erreur.for_agent())

    def test_une_erreur_applicative_renvoyee_en_200_est_levee_quand_meme(self):
        _, opener = espion({"error": {"code": "QUOTA_EXCEEDED", "retryable": True}}, 200)

        with self.assertRaises(VaEmailError) as capture:
            VaEmail(api_key="k", opener=opener).usage()

        self.assertEqual(capture.exception.code, "QUOTA_EXCEEDED")
        self.assertTrue(capture.exception.retryable)


if __name__ == "__main__":
    unittest.main()
