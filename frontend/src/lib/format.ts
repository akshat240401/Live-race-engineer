export function msToLap(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "--:--.---";
  const totalSeconds = ms / 1000;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds - minutes * 60;
  return `${minutes}:${seconds.toFixed(3).padStart(6, "0")}`;
}

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function fixed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}