import type { Metadata } from "next";
import { ForecastView } from "@/components/ForecastView";
import { money } from "@/lib/format";
import { snapshot } from "@/lib/mock";

export const metadata: Metadata = {
  title: "CardSense — What's coming",
};

export default function ForecastPage() {
  const { forecast } = snapshot;

  return (
    <main>
      <ForecastView
        forecast={forecast}
        cards={snapshot.cards}
        today={snapshot.generatedAt}
      />

      <div className="shell">
        <section className="section">
          <h2 className="section__label">If you change nothing</h2>
          <p className="doNothing">
            <span className="doNothing__figure num">
              {money(forecast.doNothingCost)}
            </span>
            <span className="doNothing__text">
              is what carrying on exactly as you are will cost you{" "}
              {forecast.doNothingWindow} — on top of the{" "}
              {money(snapshot.totals.unclaimed)} already unclaimed this quarter.
              Every date above is a chance to avoid part of it.
            </span>
          </p>
        </section>
      </div>
    </main>
  );
}
