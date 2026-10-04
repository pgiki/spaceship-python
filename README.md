# spaceship-python

A friendly Python SDK for the [Spaceship API](https://docs.spaceship.dev/) (domains, DNS, contacts).

```python
from spaceship import Spaceship

sp = Spaceship()  # reads SPACESHIP_API_KEY / SPACESHIP_API_SECRET from env
op = sp.operations.get("abc123xyz")
print(op.status)
```

## Install

```bash
pip install spaceship-python
```

Requires Python ≥ 3.12. Dependencies: `httpx`, `pydantic`, `python-dotenv`.

## Authentication

Generate an API key + secret in [API Manager](https://www.spaceship.com/application/api-manager/),
then either pass them explicitly or set environment variables:

```bash
SPACESHIP_API_KEY=...
SPACESHIP_API_SECRET=...
```

```python
sp = Spaceship(api_key="...", api_secret="...")
sp = Spaceship.from_env_file(".env.prod")
```

Grant these scopes on the key for full SDK use: `domains:read`, `domains:write`,
`domains:billing`, `domains:transfer`, `contacts:read`, `contacts:write`,
`dnsrecords:read`, `dnsrecords:write`, `asyncoperations:read`.

## Async operations

Register/renew/transfer/restore return HTTP 202 with a
`spaceship-async-operationid` header. The SDK polls for you:

```python
domain = sp.domains.register("example.com", years=1, contact=contact)  # blocks
pending = sp.domains.register("example.com", years=1, contact=contact, wait=False)
final = sp.operations.wait_for(pending.operation_id, timeout=300)
```

## Rate limits (per docs)

Availability/register/renew: 30 req / 30s (availability accepts up to 20
domains per call — the SDK chunks automatically). Domain info: 5 req/domain /
300s. Domain list: 300 req / 300s.

## Testing

There is no Spaceship sandbox, so the suite is fully offline
(mock transport, no network, no spend):

```bash
pytest
ruff check src/ tests/
```

## Roadmap

- [x] Core: config, errors, async-operation polling
- [ ] Domains: availability (with pricing), register/renew/restore/transfer, contacts
- [ ] DNS: record CRUD over whole-zone save
- [ ] PyPI 0.1.0 release
