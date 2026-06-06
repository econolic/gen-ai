# ADR-006: Live Provider Health

## Status

Accepted

## Decision

Expose live provider status through `/health` instead of treating configured
environment variables as proof of availability.

The backend performs a short cached OpenRouter completions probe with a small
`max_tokens` limit. The health response reports:

- `model_status: live` only when OpenRouter responds successfully
- `model_status: not_configured` when no key is present
- `model_status: error` when the endpoint fails
- `data_mode: live_sources_first` when `OFFLINE_DEMO_SEED_FIRST=false`
- `data_mode: offline_demo_seed_first` when deterministic seed-first mode is enabled

## Consequences

The UI can distinguish a truly live OpenRouter model from a merely configured
API key. The submitted demo can show `OpenRouter · live · live_sources_first`
and prove that live sources are active while still preserving an offline
development fallback.
