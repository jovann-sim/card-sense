const DAYS_PER_MONTH = 30.44;

/**
 * When the target is reached at the current rate of earning, or `null` if
 * there is no target to reach.
 */
export function projectArrival(
  current: number,
  target: number | null,
  pacePerMonth: number,
  fromISO: string,
): string | null {
  if (target === null || pacePerMonth <= 0) return null;

  const remaining = target - current;
  if (remaining <= 0) return fromISO.slice(0, 10);

  const days = Math.ceil((remaining / pacePerMonth) * DAYS_PER_MONTH);
  const date = new Date(fromISO);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(fromISO: string, toISO: string) {
  return Math.round(
    (new Date(toISO).getTime() - new Date(fromISO).getTime()) / 86_400_000,
  );
}

export function weeksBetween(fromISO: string, toISO: string) {
  return Math.round(daysBetween(fromISO, toISO) / 7);
}
