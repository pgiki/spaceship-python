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

For storefront pricing (Cloudflare-aware fetcher):

```bash
pip install "spaceship-python[pricing]"
playwright install chromium
```

## Storefront pricing (no API key)

The public API has no bulk TLD pricing endpoint, so the SDK can quote the
storefront pricing BFF instead (register/renew/transfer per TLD):

```python
from spaceship import StorefrontPricing

pricing = StorefrontPricing()  # fetcher="playwright" by default
for quote in pricing.fetch(["com", "org", "ai"]):
    print(quote.tld, quote.register, quote.renew, quote.transfer)
```

`StorefrontPricing(PricingConfig(...))` accepts `currency`, `batch_size`,
`fetcher="direct"` (plain HTTP, works while Cloudflare cookies are fresh) and
`fetcher="scraping_api"` (via your scraping proxy). The Playwright fetcher
opens one browser session per `fetch()` call and reuses it across all chunks.
See `examples/pricing.py`.

## Examples

Runnable end-to-end scripts in `examples/` (run from the repo root, e.g.
`python examples/portfolio.py`). ⚠️ marks scripts that can spend money or
mutate live state — those require explicit confirmation:

| Script | What it shows |
|---|---|
| `quickstart.py` | Availability check (free). |
| `check_availability.py` | Bulk checks, premium vs standard pricing, IDN. |
| `portfolio.py` | Paginated portfolio audit with expiry flags (read-only). |
| `domain_lifecycle.py` ⚠️ | `register/renew/transfer-in/restore` (charged) + `info`/`settings`; `--no-wait` async pattern. |
| `contacts.py` | Contact create/read/ensure/attributes. |
| `dns_manage.py` ⚠️ | Zone list/add/set-a/delete; dry-run by default, `--apply` + YES to write. |
| `pricing.py` | Minimal bulk TLD quotes (no API key). |
| `pricing_report.py` | Fetcher variants, cheapest-TLD ranking, CSV/Markdown export. |
| `error_handling.py` | Error shapes, unsupported endpoints, rate limits (offline). |

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
- [x] Domains: availability (with pricing), register/renew/restore/transfer, contacts
- [x] DNS: record CRUD over whole-zone save
- [ ] PyPI 0.1.0 release
