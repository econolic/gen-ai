# ADR-005: Approval And Fail Closed

## Status

Accepted

## Decision

Require human approval for web-backed and hybrid plans, validate generated plans before execution, and return controlled row-level errors instead of raw exceptions.

Safe local table calculations can execute immediately. Web-backed and hybrid
plans move to `awaiting_approval`, show the generated route, target column,
source columns, operation preview, confidence, and estimated external calls, and
allow the target column to be edited before approval.

Ambiguous or unsupported tasks move to clarification/fail-closed states with a
concrete message instead of silently guessing.

## Consequences

Risky or ambiguous runs pause before spending external calls, failed cells retain
evidence and reasons, and partial success files remain downloadable. API and
gateway failures use controlled error envelopes so the UI can display clear
messages instead of raw tracebacks.
