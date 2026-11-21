const num = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 2 });

export const money = (value: number, currency = "EUR") => `${currency} ${num.format(value)}`;
export const moneyCompact = (value: number, currency = "EUR") => `${currency} ${compact.format(value)}`;

export function cell(value: unknown): string {
  if (value === null || value === undefined) return "—"; // visibly missing (e.g. no PO / approver)
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : num.format(value);
  if (typeof value === "object") return Object.entries(value).map(([k, v]) => `${k} ${num.format(Number(v))}`).join(" · ");
  return String(value);
}
