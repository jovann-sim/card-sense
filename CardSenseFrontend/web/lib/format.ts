/**
 * All dates render in a fixed zone rather than the viewer's.
 *
 * These pages are statically prerendered, so the server formats at build time
 * and the browser reformats on hydration. Left to local time those two
 * disagree the moment the build host and the viewer are in different zones —
 * Cloud Run runs UTC — and React reports a hydration mismatch. Pinning the
 * zone makes the output deterministic. When accounts become real, switch this
 * to the zone stored on the user and format on the client only.
 */
const DISPLAY_TZ = "America/New_York";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

const usdWhole = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const units = new Intl.NumberFormat("en-US");

/**
 * Calendar dates in the fixtures are date-only ("2026-08-19"), which parses as
 * UTC midnight. Formatting those in any western zone rolls them back a day, so
 * they are read in UTC and render exactly as written.
 */
const dayMonthFmt = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

const clockFmt = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  timeZone: DISPLAY_TZ,
});

const longDayFmt = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: DISPLAY_TZ,
});

export const money = (n: number) => usd.format(n);
export const moneyWhole = (n: number) => usdWhole.format(n);
export const count = (n: number) => units.format(n);

export const pct = (n: number, of: number) =>
  of === 0 ? 0 : Math.min(100, (n / of) * 100);

export const dayMonth = (iso: string) => dayMonthFmt.format(new Date(iso));
export const timeOfDay = (iso: string) => clockFmt.format(new Date(iso));
export const longDay = (iso: string) => longDayFmt.format(new Date(iso));

/** Whole days from `from` until `iso`, floored at 0. */
export function daysUntil(iso: string, from: string) {
  const ms = new Date(iso).getTime() - new Date(from).getTime();
  return Math.max(0, Math.ceil(ms / 86_400_000));
}
