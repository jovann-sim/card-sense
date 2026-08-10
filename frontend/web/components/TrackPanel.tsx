import Link from "next/link";
import type { RewardTrack, TrackValuation } from "@/lib/types";
import { count, money } from "@/lib/format";

const TRACK_LABEL: Record<RewardTrack, string> = {
  points: "Points",
  cashback: "Cash back",
  miles: "Air miles",
};

export function TrackPanel({
  tracks,
  recommended,
  rationale,
  hasPreference,
}: {
  tracks: TrackValuation[];
  recommended: RewardTrack;
  rationale: string;
  hasPreference: boolean;
}) {
  return (
    <>
      <div className="tracks">
        {tracks.map((t) => (
          <article
            key={t.track}
            className="track"
            data-picked={t.track === recommended}
          >
            <h3 className="track__name">
              {TRACK_LABEL[t.track]}
              {t.track === recommended && <span>Agent&rsquo;s pick</span>}
            </h3>
            <p className="track__value">{money(t.nominal)}</p>
            <p className="track__math">
              {t.rate === 1
                ? "No conversion applied"
                : `${count(t.rawUnits)} ${t.unitLabel} × $${t.rate.toFixed(4)}`}
            </p>
            <p className="track__source">{t.source}</p>
          </article>
        ))}
      </div>

      <p className="rationale">
        <strong>
          {hasPreference
            ? "Measured against your stated preference."
            : "No preference set."}
        </strong>{" "}
        {rationale}
      </p>

      {/* Not a dead end: the agent guessed, and here is where you correct it. */}
      <p className="rationale__cta">
        <Link href="/goals" className="record__link">
          {hasPreference ? "Change your goal →" : "Set a goal instead →"}
        </Link>
      </p>
    </>
  );
}
