# ADR-001: LangGraph Orchestration

## Status

Accepted

## Decision

Use LangGraph as the enrichment workflow boundary for profiling, planning, execution, validation, output writing, and report generation.

The graph flow is:

```text
profile_workbook
-> plan_task
-> prepare_execution
-> execute_enrichment
-> validate_results
-> write_output
-> build_report
```

For source-backed workbooks above the configured threshold, execution can switch
to chunk fan-out and merge row updates after concurrent processing.

## Consequences

The backend keeps every run observable as a typed state transition, supports
fan-out for large source-backed workbooks, and can fall back to a sequential
graph runner in constrained local environments. Reports preserve the generated
plan, workbook profile, row updates, evidence, warnings, performance metrics,
and fan-out metadata.
