import Link from "next/link";
import type { AgentRun } from "@/lib/types";
import { timeOfDay } from "@/lib/format";
import { Nav } from "./Nav";

/**
 * App chrome. The top row makes the autonomous run legible at a glance — which
 * agents ran, when, and which one is operating on incomplete input. The second
 * row is section navigation.
 */
export function AgentRail({
  agents,
  generatedAt,
}: {
  agents: AgentRun[];
  generatedAt: string;
}) {
  const hasRun = agents.some((agent) => agent.status !== "not-run");

  return (
    <header className="rail">
      <div className="shell rail__inner">
        <Link href="/" className="rail__mark">
          Card<span>Sense</span>
        </Link>

        <ul className="rail__agents">
          {agents.map((agent) => (
            <li
              key={agent.id}
              className="agent"
              data-status={agent.status}
              title={
                agent.note ??
                (agent.lastRunAt
                  ? `Last run ${timeOfDay(agent.lastRunAt)}`
                  : "Not run yet")
              }
            >
              <span className="agent__dot" aria-hidden />
              {agent.label}
              {agent.status === "degraded" && " · degraded"}
              {agent.status === "not-run" && " · not run"}
            </li>
          ))}
        </ul>

        <p className="rail__stamp">
          {hasRun ? `Snapshot ${timeOfDay(generatedAt)}` : "No agent run yet"}
        </p>
      </div>

      <div className="shell">
        <Nav />
      </div>
    </header>
  );
}
