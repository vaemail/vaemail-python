# vaemail — Python SDK

Email infrastructure for AI agents and applications. Send transactional email,
authenticate sending domains, track delivery, and diagnose deliverability.

No dependencies: the SDK uses only the standard library, so it installs without
pulling anything behind it.

```bash
pip install vaemail
```

## Send an email

```python
from vaemail import VaEmail

client = VaEmail(api_key="your-api-key")

client.send({
    "to": "customer@example.com",
    "subject": "Your order is on its way",
    "html": "<p>Tracking number: 1Z999</p>",
}, idempotency_key="order-4711")
```

The idempotency key makes the call safe to replay for 24 hours: retrying after a
timeout will not send a second email.

## Try before sending

```python
client.validate({"to": "customer@example.com", "subject": "Hi", "html": "<p>Hi</p>"})
```

Same checks as a real send — key scope, quotas, sending domain, suppression
list — but nothing leaves. Useful when an agent builds a message on its own.

## Identify the account and use sandbox mode

`GET /api/v1/me` returns the tenant, non-secret key metadata, scopes and `mode`
(`live` or `sandbox`). Contacts support an optional tenant-unique
`external_reference` for CRM identifiers and upserts.

With a sandbox key, reads are normal but every POST, PUT, PATCH and DELETE is fully
validated inside a transaction that is always rolled back. No database row, job,
email, SMS, webhook or outbound HTTP call survives. The response has
`X-VaEmail-Sandbox: 1` and JSON objects include `sandbox: true`; idempotency keys are
not persisted. This is an integration simulation, not proof of delivery.

## Authenticate a sending domain

```python
result = client.add_domain("news.example.com", dkim_tokens=["aaa111", "bbb222", "ccc333"])

for record in result["data"]["dns_records"]:
    if record["publishable"]:
        print(record["type"], record["host"], "->", record["value"])
```

The three DKIM tokens come from Amazon SES when the domain identity is created.
Every record says whether it is `publishable` as-is: a value that still depends
on something unknown is flagged instead of being handed over, so an agent never
publishes a record that would break the domain's authentication.

## Errors say what to do next

```python
from vaemail import VaEmailError

try:
    client.send({"to": "customer@example.com"})
except VaEmailError as error:
    print(error.code)        # DOMAIN_NOT_VERIFIED
    print(error.retryable)   # False
    print(error.for_agent()) # reason, corrective action, whether to retry
```

## Everything else

`capabilities()`, `health()`, `get_message()`, `list_messages()`,
`list_domains()`, `verify_domain()`, `dns_records()`,
`diagnose_deliverability()`, `list_suppressions()`, `usage()`, `audit_logs()`.

Full API reference: <https://vaemail.fr/docs/api>

## Connecter Stripe

La connexion Stripe utilise une clé restreinte `rk_live_` ou `rk_test_`, avec Customers
en lecture et Webhook Endpoints en écriture. Les clés secrètes `sk_` sont refusées. La
clé n'est jamais renvoyée par l'API : l'état de la connexion expose seulement ses quatre
derniers caractères, ainsi que ceux du token du webhook.

Les routes REST sont :

- `GET /api/v1/integrations/stripe` pour lire l'état, sans secret ;
- `POST /api/v1/integrations/stripe` avec `{"api_key":"rk_live_..."}` pour créer ou
  réconcilier le webhook (`settings.write`) ;
- `DELETE /api/v1/integrations/stripe` pour supprimer le webhook puis la connexion locale.
  Cette action irréversible demande une validation humaine explicite.

Stripe appelle ensuite `POST /api/v1/webhooks/stripe/{token}`. Cette route publique
vérifie l'en-tête `Stripe-Signature` ; elle ne reçoit pas la clé API VaEmail.

Les quatre événements pris en charge déclenchent les automatisations suivantes :

| Événement Stripe | Déclencheur VaEmail |
| --- | --- |
| `invoice.payment_failed` | `stripe_payment_failed` (`payment_failed`) |
| `customer.subscription.created` | `stripe_subscription_created` (`subscription_created`) |
| `customer.subscription.deleted` | `stripe_subscription_deleted` (`subscription_deleted`) |
| `checkout.session.completed` | `stripe_checkout_completed` (`checkout_completed`) |

## Tests

```bash
python -m unittest discover -s tests
```

MIT licensed.
