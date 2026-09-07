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

## Tests

```bash
python -m unittest discover -s tests
```

MIT licensed.
