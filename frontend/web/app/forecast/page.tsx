import type { Metadata } from "next";
import { ForecastView } from "@/components/ForecastView";
import { money } from "@/lib/format";
import { getForecast, getSnapshot, HORIZONS } from "@/lib/api";

export const metadata: Metadata = {
  title: "CardSense — What's coming",
};

/** The horizon lives in the URL so a projection can be linked to and shared. */
function horizonFrom(value: string | string[] | undefined): number {
  const months = Number(Array.isArray(value) ? value[0] : value);
  return HORIZONS.includes(months as (typeof HORIZONS)[number]) ? months : 1;
}

export default async function ForecastPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const months = horizonFrom((await searchParams).months);
  const snapshot = await getSnapshot();
  // Falls back to the snapshot's own projection if the re-projection fails, so
  // a dead endpoint costs the horizon selector rather than the whole page.
  const forecast = (await getForecast(months)) ?? snapshot.forecast;

  return (
    <main>
      <ForecastView
        key={`${snapshot.generatedAt}-${forecast.horizonMonths}`}
        forecast={forecast}
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
