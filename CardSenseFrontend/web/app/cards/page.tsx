import type { Metadata } from "next";
import { CardsView } from "@/components/CardsView";
import { getSnapshot } from "@/lib/api";

export const metadata: Metadata = {
  title: "CardSense — Cards",
};

export default async function CardsPage() {
  const snapshot = await getSnapshot();
  const unread = snapshot.wallet.filter((c) => c.parseStatus !== "parsed");

  return (
    <main>
      <section className="shell hero hero--sub">
        <p className="hero__eyebrow">Cards</p>

        <h1 className="hero__claim hero__claim--lead">
          What the agent read, where it read it, and when it last checked.
        </h1>

        <p className="hero__sub">
          Every reward rate on this site traces back to a document. {unread.length}{" "}
          of {snapshot.wallet.length} cards are currently running on rules that
          are stale or missing, and those cards are excluded from comparisons
          rather than guessed at.
        </p>
      </section>

      <div className="shell section">
        <CardsView wallet={snapshot.wallet} catalog={snapshot.catalog} />
      </div>
    </main>
  );
}
