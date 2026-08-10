import type { Metadata } from "next";
import { GoalsView } from "@/components/GoalsView";
import { getSnapshot } from "@/lib/api";

export const metadata: Metadata = {
  title: "CardSense — Goals",
};

export default async function GoalsPage() {
  const snapshot = await getSnapshot();
  return (
    <main>
      <section className="shell hero hero--sub">
        <p className="hero__eyebrow">Goals</p>

        <h1 className="hero__claim hero__claim--lead">
          Tell the agent what you are actually trying to reach.
        </h1>

        <p className="hero__sub">
          Points, cash back and miles are only comparable once you say which one
          you want. Give it a number and a date and the strategy agent stops
          optimising in the abstract — it starts telling you whether you will
          get there.
        </p>
      </section>

      <div className="shell">
        <GoalsView
          key={snapshot.generatedAt}
          goal={snapshot.goal}
          planned={snapshot.planned}
          tracks={snapshot.tracks}
          today={snapshot.generatedAt}
        />
      </div>
    </main>
  );
}
