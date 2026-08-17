import type { AgentId, AgentQualityReport } from "@/lib/types";
import { longDay, timeOfDay } from "@/lib/format";


const LABELS: Record<AgentId, string> = {
  ingestion: "Ingestion",
  "card-intelligence": "Card intelligence",
  strategy: "Strategy",
  forecast: "Forecast",
  advisory: "Advisory",
};

function percentage(value: number | null) {
  return value === null ? "Not measured" : `${(value * 100).toFixed(1)}%`;
}

function duration(value: number | null) {
  if (value === null) return "Not measured";
  return value < 1_000 ? `${Math.round(value)}ms` : `${(value / 1_000).toFixed(1)}s`;
}

function cost(value: number | null) {
  if (value === null) return "Not measured";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

export function AgentQuality({ quality }: { quality: AgentQualityReport | null }) {
  if (!quality) {
    return (
      <section className="section">
        <h2 className="section__label">Agent quality</h2>
        <p className="empty-state">
          The quality report is unavailable. Start the updated backend to run
          the deterministic evaluation gates.
        </p>
      </section>
    );
  }

  const liveByAgent = new Map(quality.live.agents.map((agent) => [agent.id, agent]));
  const modelByAgent = new Map<
    AgentId,
    AgentQualityReport["modelCost"]["agents"][number]
  >(quality.modelCost.agents.map((agent) => [agent.id, agent]));
  const engineSummary = Object.entries(quality.live.engines)
    .map(([engine, count]) => `${engine} ${count}`)
    .join(" · ") || "No completed runs";

  return (
    <section className="section">
      <h2 className="section__label">Agent quality</h2>
      <p className="section__note">
        Auditable golden cases beside evidence from real persisted runs. Last
        evaluated {longDay(quality.golden.evaluatedAt)} at {timeOfDay(quality.golden.evaluatedAt)}.
      </p>

      <div className="quality__metrics">
        <article className="quality__metric" data-state={quality.golden.passed ? "pass" : "fail"}>
          <p className="quality__value num">
            {quality.golden.casesPassed}/{quality.golden.casesTotal}
          </p>
          <p className="quality__label">Golden cases</p>
          <p className="quality__detail">
            {quality.golden.assertionsPassed}/{quality.golden.assertionsTotal} assertions
          </p>
        </article>
        <article className="quality__metric" data-state={quality.golden.unsupportedClaims === 0 ? "pass" : "fail"}>
          <p className="quality__value num">{quality.golden.unsupportedClaims}</p>
          <p className="quality__label">Unsupported claims</p>
          <p className="quality__detail">Detected by Advisory grounding gates</p>
        </article>
        <article className="quality__metric">
          <p className="quality__value num">{percentage(quality.live.degradedRate)}</p>
          <p className="quality__label">Degraded runs</p>
          <p className="quality__detail">
            {quality.live.degradedRuns} of {quality.live.terminalRuns} completed or failed runs
          </p>
        </article>
        <article className="quality__metric">
          <p className="quality__value num">{duration(quality.live.medianRunDurationMs)}</p>
          <p className="quality__label">Median run time</p>
          <p className="quality__detail">{engineSummary}</p>
        </article>
        <article className="quality__metric" data-state={quality.modelCost.failedCalls === 0 ? "pass" : "fail"}>
          <p className="quality__value num">
            {quality.modelCost.successfulCalls}/{quality.modelCost.calls}
          </p>
          <p className="quality__label">Gemini calls</p>
          <p className="quality__detail">{quality.modelCost.failedCalls} unavailable or failed</p>
        </article>
        <article className="quality__metric">
          <p className="quality__value num">{quality.modelCost.totalTokens.toLocaleString()}</p>
          <p className="quality__label">Model tokens</p>
          <p className="quality__detail">
            {quality.modelCost.inputTokens.toLocaleString()} in · {quality.modelCost.outputTokens.toLocaleString()} out · {quality.modelCost.thinkingTokens.toLocaleString()} thinking
          </p>
        </article>
        <article className="quality__metric">
          <p className="quality__value num">{cost(quality.modelCost.estimatedUsd)}</p>
          <p className="quality__label">Estimated model cost</p>
          <p className="quality__detail">USD · recorded call-time rates</p>
        </article>
      </div>

      <div className="quality__table" role="table" aria-label="Per-agent quality">
        <div className="quality__row quality__row--head" role="row">
          <span role="columnheader">Agent</span>
          <span role="columnheader">Golden</span>
          <span role="columnheader">Live stages</span>
          <span role="columnheader">Model calls</span>
          <span role="columnheader">Median</span>
          <span role="columnheader">Degraded / failed</span>
        </div>
        {(Object.keys(LABELS) as AgentId[]).map((id) => {
          const golden = quality.golden.agents[id];
          const live = liveByAgent.get(id);
          const model = modelByAgent.get(id);
          return (
            <div className="quality__row" role="row" key={id}>
              <strong role="cell">{LABELS[id]}</strong>
              <span role="cell" className="num">{golden.casesPassed}/{golden.casesTotal}</span>
              <span role="cell" className="num">{live?.executions ?? 0}</span>
              <span role="cell" className="num">{model?.calls ?? 0}</span>
              <span role="cell" className="num">{duration(live?.medianDurationMs ?? null)}</span>
              <span role="cell" className="num">{live?.degraded ?? 0} / {live?.failed ?? 0}</span>
            </div>
          );
        })}
      </div>

      <div className="quality__notes">
        <p>
          <strong>Recommendation outcomes:</strong>{" "}
          {quality.outcomes.status === "measured"
            ? `${quality.outcomes.evaluated} evaluated · mean absolute error $${quality.outcomes.meanAbsoluteError?.toFixed(2)}`
            : quality.outcomes.note}
        </p>
        <p>
          <strong>Model usage:</strong> {quality.modelCost.note}
        </p>
      </div>
    </section>
  );
}
