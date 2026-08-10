import type { AgentRun } from "@/lib/types";

export function SiteFooter({ agents }: { agents: AgentRun[] }) {
  const degraded = agents.filter((a) => a.status === "degraded");

  return (
    <footer className="footer">
      <div className="shell">
        <p className="footer__disclaimer">
          CardSense is informational only and is not licensed financial advice.
          Reward figures are estimates built from published card terms and
          sandbox transaction data; confirm anything that matters with your
          issuer. CardSense never stores or enters a card number.
        </p>
        <p className="footer__meta">
          {degraded.length > 0
            ? `${degraded.length} agent running degraded — ${degraded[0].note}`
            : "All agents nominal."}
        </p>
      </div>
    </footer>
  );
}
