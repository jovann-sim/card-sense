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
              title={agent.note ?? `Last run ${timeOfDay(agent.lastRunAt)}`}
            >
              <span className="agent__dot" aria-hidden />
              {agent.label}
              {agent.status === "degraded" && " · degraded"}
            </li>
          ))}
        </ul>

        <p className="rail__stamp">Last run {timeOfDay(generatedAt)}</p>
      </div>

      <div className="shell">
        <Nav />
      </div>
    </header>
  );
}
