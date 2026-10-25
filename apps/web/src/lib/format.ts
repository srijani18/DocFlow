const BYTE_UNITS = ["B", "KB", "MB", "GB"];

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

const DATE_TIME = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

/** An exact decimal string from the API, shown with its currency (en-IN grouping). */
export function formatMoney(amount: string | null, currency: string | null): string {
  if (amount === null) return "—";
  const value = Number(amount);
  if (currency === null) return value.toLocaleString("en-IN", { minimumFractionDigits: 2 });
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(value);
}
