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

/**
 * Singapore dollars are the base currency. A card whose own terms are
 * denominated elsewhere keeps its currency and is labelled — see moneyIn —
 * rather than being converted at a rate nobody chose.
 */
export const BASE_CURRENCY = "SGD";
const LOCALE = "en-SG";

const base = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: BASE_CURRENCY,
  minimumFractionDigits: 2,
});

const baseWhole = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: BASE_CURRENCY,
  maximumFractionDigits: 0,
});

const byCurrency = new Map<string, Intl.NumberFormat>();

/** Format in a card's own currency, always showing which one it is. */
export function moneyIn(amount: number, currency?: string | null): string {
  const code = (currency || BASE_CURRENCY).toUpperCase();
  if (code === BASE_CURRENCY) return base.format(amount);
  let formatter = byCurrency.get(code);
  if (!formatter) {
    formatter = new Intl.NumberFormat(LOCALE, {
      style: "currency",
      currency: code,
      currencyDisplay: "code",
      minimumFractionDigits: 2,
    });
    byCurrency.set(code, formatter);
  }
  return formatter.format(amount);
}

const units = new Intl.NumberFormat(LOCALE);

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

export const money = (n: number) => base.format(n);
export const moneyWhole = (n: number) => baseWhole.format(n);
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
