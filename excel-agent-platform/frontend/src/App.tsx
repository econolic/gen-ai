import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  apiDownloadUrl,
  apiGet,
  apiPatchForm,
  apiPost,
  apiPostForm,
  formatApiError,
} from "./apiClient";

type RunStatus = {
  run_id: string;
  state:
    | "queued"
    | "running"
    | "awaiting_approval"
    | "awaiting_clarification"
    | "completed"
    | "failed";
  progress: number;
  message: string;
  output_path?: string;
  report_path?: string;
  plan?: {
    target_sheet: string;
    target_column: string;
    operation: string;
    unit?: string;
    confidence: number;
    estimated_external_calls: number;
    route: { route: string; reason: string };
    source_columns: string[];
    operations: {
      type: string;
      target_column: string;
      source_columns: string[];
      entity_columns?: string[];
      attribute?: string;
      unit?: string;
      value_type?: string;
      expression?: string;
    }[];
  };
  profile?: {
    sheets: {
      name: string;
      row_count: number;
      column_count: number;
      columns: { name: string; dtype: string; non_null_count: number; null_count: number }[];
    }[];
  };
  preview: Record<string, unknown>[];
  updates: {
    row_index: number;
    target_column: string;
    value?: unknown;
    confidence: number;
    error?: string;
    evidence: {
      kind: string;
      title: string;
      url?: string;
      confidence?: number;
      metadata?: Record<string, unknown>;
    }[];
  }[];
  performance: Record<string, number | string | boolean>;
  warnings: string[];
  errors: string[];
  clarification_question?: string;
};

type McpHealth = {
  status: string;
  strict: boolean;
  servers: Record<string, { status: string; missing_tools: string[] }>;
};

type HealthStatus = {
  status: string;
  provider: string;
  model: string;
  data_mode: string;
  model_configured: boolean;
  model_status: "live" | "not_configured" | "error" | string;
  model_live: boolean;
  model_error?: string | null;
};

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [task, setTask] = useState(
    "Find the straight-line distance between the capitals in kilometers for the column distance"
  );
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [clarification, setClarification] = useState("");
  const [clarifying, setClarifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [mcpHealth, setMcpHealth] = useState<McpHealth | null>(null);
  const [approving, setApproving] = useState(false);
  const [savingPlan, setSavingPlan] = useState(false);
  const [targetColumn, setTargetColumn] = useState("");

  const isBusy =
    status?.state === "queued" ||
    status?.state === "running" ||
    submitting ||
    clarifying ||
    approving ||
    savingPlan;

  async function refresh(id = runId) {
    await refreshHealth();
    if (!id) return;
    setStatus(await apiGet<RunStatus>(`/api/runs/${id}`));
  }

  async function refreshHealth() {
    setHealth(await apiGet<HealthStatus>("/health"));
    setMcpHealth(await apiGet<McpHealth>("/health/mcp"));
  }

  useEffect(() => {
    refreshHealth().catch((err) => setError(formatApiError(err)));
  }, []);

  useEffect(() => {
    if (
      !runId ||
      status?.state === "completed" ||
      status?.state === "failed" ||
      status?.state === "awaiting_approval" ||
      status?.state === "awaiting_clarification"
    )
      return;
    const interval = window.setInterval(() => {
      refresh(runId).catch((err) => setError(formatApiError(err)));
    }, 1200);
    return () => window.clearInterval(interval);
  }, [runId, status?.state]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Select an Excel file first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setStatus(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("task_description", task);
      const data = await apiPostForm<{ run_id: string }>("/api/runs", formData);
      setRunId(data.run_id);
      setClarification("");
      await refresh(data.run_id);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function onClarify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!runId || !clarification.trim()) return;
    setClarifying(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("clarification", clarification);
      await apiPostForm<{ run_id: string; status: string }>(`/api/runs/${runId}/clarify`, formData);
      setClarification("");
      await refresh(runId);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setClarifying(false);
    }
  }

  async function onApprove() {
    if (!runId) return;
    setApproving(true);
    setError(null);
    try {
      await apiPost<{ run_id: string; status: string }>(`/api/runs/${runId}/approve`);
      await refresh(runId);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setApproving(false);
    }
  }

  async function onSaveTarget() {
    if (!runId || !targetColumn.trim()) return;
    setSavingPlan(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("target_column", targetColumn.trim());
      await apiPatchForm(`/api/runs/${runId}/plan`, formData);
      await refresh(runId);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSavingPlan(false);
    }
  }

  useEffect(() => {
    if (status?.plan?.target_column) {
      setTargetColumn(status.plan.target_column);
    }
  }, [status?.plan?.target_column]);

  const columns = useMemo(() => {
    if (!status?.preview?.length) return [];
    return Object.keys(status.preview[0]).filter((key) => key !== "_row_index");
  }, [status?.preview]);

  const updateByCell = useMemo(() => {
    const map = new Map<string, NonNullable<RunStatus["updates"]>[number]>();
    for (const update of status?.updates ?? []) {
      map.set(`${update.row_index}:${update.target_column}`, update);
    }
    return map;
  }, [status?.updates]);

  const evidenceItems = useMemo(() => {
    return (status?.updates ?? [])
      .flatMap((update) =>
        update.evidence.map((evidence) => ({
          ...evidence,
          rowIndex: update.row_index,
          targetColumn: update.target_column,
        }))
      )
      .filter((evidence) => evidence.kind !== "calculation")
      .slice(0, 8);
  }, [status?.updates]);

  const failedUpdates = useMemo(() => {
    return (status?.updates ?? []).filter((update) => update.error).slice(0, 8);
  }, [status?.updates]);

  return (
    <main className="shell">
      <section className="workspace">
        <div className="topbar">
          <div className="brand">
            <FileSpreadsheet size={24} aria-hidden="true" />
            <div>
              <h1>Excel Agent Platform</h1>
              <p>Typed enrichment runs with evidence reports</p>
            </div>
          </div>
          <div className="topbarActions">
            {health && (
              <div
                className="modelBadge"
                title={`${health.provider} ${health.model} · ${health.data_mode}${
                  health.model_error ? ` · ${health.model_error}` : ""
                }`}
              >
                <Sparkles size={16} aria-hidden="true" />
                <div>
                  <span>{health.model}</span>
                  <small className={health.model_status === "live" ? "statusActive" : "statusMuted"}>
                    {health.provider} · {health.model_status} · {health.data_mode}
                  </small>
                </div>
              </div>
            )}
            {mcpHealth && (
              <div className="modelBadge" title={`MCP ${mcpHealth.status}`}>
                <ShieldCheck size={16} aria-hidden="true" />
                <div>
                  <span>MCP {mcpHealth.status}</span>
                  <small className={mcpHealth.status === "ok" ? "statusActive" : "statusMuted"}>
                    {mcpHealth.strict ? "strict" : "fallback allowed"}
                  </small>
                </div>
              </div>
            )}
            <button
              className="iconButton"
              type="button"
              onClick={() => refresh().catch((err) => setError(String(err)))}
              title="Refresh run"
            >
              <RefreshCw size={18} aria-hidden="true" />
            </button>
          </div>
        </div>

        <form className="runForm" onSubmit={onSubmit}>
          <label className="fileInput">
            <FileSpreadsheet size={20} aria-hidden="true" />
            <span>{file ? file.name : "Select .xlsx file"}</span>
            <input
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <textarea
            value={task}
            onChange={(event) => setTask(event.target.value)}
            rows={3}
            aria-label="Task description"
          />
          <button className="primaryButton" type="submit" disabled={isBusy}>
            {isBusy ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            <span>{isBusy ? "Running" : "Run"}</span>
          </button>
        </form>

        {error && (
          <div className="alert danger">
            <AlertTriangle size={18} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {status && (
          <div className="statusBand">
            <div className="statusText">
              {status.state === "completed" ? (
                <CheckCircle2 size={20} aria-hidden="true" />
              ) : status.state === "failed" ? (
                <AlertTriangle size={20} aria-hidden="true" />
              ) : status.state === "awaiting_clarification" ? (
                <AlertTriangle size={20} aria-hidden="true" />
              ) : status.state === "awaiting_approval" ? (
                <ShieldCheck size={20} aria-hidden="true" />
              ) : (
                <Loader2 className="spin" size={20} aria-hidden="true" />
              )}
              <span>{status.message || status.state}</span>
            </div>
            <progress value={status.progress} max={1} />
            <div className="actions">
              <a
                className={status.state === "completed" ? "iconButton linkButton" : "iconButton disabled"}
                href={apiDownloadUrl(`/api/runs/${status.run_id}/download`)}
                title="Download workbook"
              >
                <Download size={18} aria-hidden="true" />
              </a>
              <a
                className={status.state === "completed" ? "iconButton linkButton" : "iconButton disabled"}
                href={apiDownloadUrl(`/api/runs/${status.run_id}/report`)}
                title="Download report"
              >
                JSON
              </a>
            </div>
          </div>
        )}
      </section>

      {status?.state === "awaiting_approval" && (
        <section className="approvalPanel">
          <div>
            <h2>Plan Approval</h2>
            <p>{status.plan?.route.reason ?? "Review the generated plan before web-backed execution."}</p>
          </div>
          <div className="approvalControls">
            <label>
              <span>Target column</span>
              <input
                value={targetColumn}
                onChange={(event) => setTargetColumn(event.target.value)}
                aria-label="Target column"
              />
            </label>
            <button className="secondaryButton" type="button" disabled={isBusy} onClick={onSaveTarget}>
              Save target
            </button>
            <button className="primaryButton" type="button" disabled={isBusy} onClick={onApprove}>
              {approving ? <Loader2 className="spin" size={18} /> : <ShieldCheck size={18} />}
              <span>{approving ? "Approving" : "Approve"}</span>
            </button>
          </div>
        </section>
      )}

      {status?.state === "awaiting_clarification" && (
        <section className="clarificationPanel">
          <div>
            <h2>Clarification</h2>
            <p>{status.clarification_question ?? status.message}</p>
          </div>
          <form className="clarificationForm" onSubmit={onClarify}>
            <textarea
              value={clarification}
              onChange={(event) => setClarification(event.target.value)}
              rows={3}
              aria-label="Clarification"
            />
            <button className="primaryButton" type="submit" disabled={isBusy || !clarification.trim()}>
              {clarifying ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              <span>{clarifying ? "Resuming" : "Resume"}</span>
            </button>
          </form>
        </section>
      )}

      {status?.plan && (
        <section className="panelGrid">
          <article className="panel">
            <h2>Plan</h2>
            <dl>
              <dt>Route</dt>
              <dd>{status.plan.route.route}</dd>
              <dt>Confidence</dt>
              <dd>{Math.round((status.plan.confidence ?? 0) * 100)}%</dd>
              <dt>Reason</dt>
              <dd>{status.plan.route.reason}</dd>
              <dt>Operation</dt>
              <dd>{status.plan.operation}</dd>
              <dt>Target</dt>
              <dd>
                {status.plan.target_sheet}.{status.plan.target_column}
              </dd>
              <dt>Unit</dt>
              <dd>{status.plan.unit ?? "none"}</dd>
              <dt>Sources</dt>
              <dd>{status.plan.source_columns.join(", ")}</dd>
              <dt>Est. calls</dt>
              <dd>{status.plan.estimated_external_calls ?? 0}</dd>
              <dt>DSL</dt>
              <dd>
                {(status.plan.operations ?? [])
                  .map((operation) =>
                    [operation.type, operation.attribute, operation.value_type].filter(Boolean).join(":")
                  )
                  .join(", ")}
              </dd>
            </dl>
          </article>

          <article className="panel">
            <h2>Performance</h2>
            <div className="metricGrid">
              <div>
                <span>{String(status.performance?.row_count ?? status.profile?.sheets?.[0]?.row_count ?? 0)}</span>
                <small>Rows</small>
              </div>
              <div>
                <span>{String(status.performance?.external_calls ?? status.plan.estimated_external_calls ?? 0)}</span>
                <small>External calls</small>
              </div>
              <div>
                <span>{String(status.performance?.cache_hits ?? 0)}</span>
                <small>Cache hits</small>
              </div>
              <div>
                <span>{String(status.performance?.cache_hit_rate ?? 0)}</span>
                <small>Hit rate</small>
              </div>
              <div>
                <span>{String(status.performance?.max_concurrency ?? 0)}</span>
                <small>Concurrency</small>
              </div>
              <div>
                <span>{String(status.performance?.failed_updates ?? failedUpdates.length)}</span>
                <small>Failed cells</small>
              </div>
            </div>
          </article>

          <article className="panel">
            <h2>Profile</h2>
            <ul className="logList">
              {(status.profile?.sheets?.[0]?.columns ?? []).map((column) => (
                <li key={column.name}>
                  {column.name} · {column.dtype} · {column.non_null_count} values
                </li>
              ))}
              {!status.profile?.sheets?.[0]?.columns?.length && <li>Profile is not ready</li>}
            </ul>
          </article>
        </section>
      )}

      {status?.plan && (
        <section className="panelGrid">
          <article className="panel">
            <h2>Source Evidence</h2>
            <ul className="logList evidenceList">
              {evidenceItems.map((item, index) => (
                <li key={`${item.kind}-${item.rowIndex}-${index}`}>
                  <strong>{item.kind}</strong>
                  <span>
                    row {item.rowIndex + 2} · {item.targetColumn} · {item.title}
                  </span>
                </li>
              ))}
              {!evidenceItems.length && <li>No source evidence yet</li>}
            </ul>
          </article>

          <article className="panel">
            <h2>Warnings & Failed Rows</h2>
            <ul className="logList">
              {[...(status.warnings ?? []), ...(status.errors ?? [])].map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
              {failedUpdates.map((update) => (
                <li key={`${update.row_index}-${update.target_column}`}>
                  row {update.row_index + 2} · {update.target_column}: {update.error}
                </li>
              ))}
              {!status.warnings.length && !status.errors.length && !failedUpdates.length && <li>No warnings</li>}
            </ul>
          </article>
        </section>
      )}

      {status?.preview?.length ? (
        <section className="tableWrap">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {status.preview.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => {
                    const realRowIndex = Number(row._row_index ?? rowIndex);
                    const update = updateByCell.get(`${realRowIndex}:${column}`);
                    return (
                      <td key={column}>
                        <span>{String(row[column] ?? "")}</span>
                        {update && (
                          <small className={update.error ? "cellMeta errorMeta" : "cellMeta"}>
                            {update.error ? "failed" : `${Math.round(update.confidence * 100)}%`}
                          </small>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}

export default App;
