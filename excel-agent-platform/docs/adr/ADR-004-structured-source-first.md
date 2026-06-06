# ADR-004: Structured Source First

## Status

Accepted

## Decision

Resolve facts from live structured Wikidata/Wikipedia records before using
Serper search and LLM snippet extraction. Offline demo seeds are available as a
deterministic development fallback and can be promoted to first priority only
when `OFFLINE_DEMO_SEED_FIRST=true`.

## Consequences

The submitted live demo shows real `WIKIDATA` evidence while still preserving a
stable offline path for development or provider outages. Exact fact caching
reduces repeat external calls, and web search remains a fallback rather than the
default source.
