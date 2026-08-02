/** Tests des utilitaires de formatage. */

import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDelta,
  formatScore,
  toNumber,
} from "@/lib/format";

describe("format", () => {
  test("formatCurrency", () => {
    const formatted = formatCurrency("120.00", "EUR");
    expect(formatted).toMatch(/120,00/);
    expect(formatted).toContain("€");
    expect(formatCurrency(null, "EUR")).toBe("—");
    expect(formatCurrency("", "EUR")).toBe("—");
    expect(formatCurrency(undefined, "EUR")).toBe("—");
    expect(formatCurrency("abc", "EUR")).toBe("—");
  });

  test("formatDate", () => {
    expect(formatDate("2026-01-15")).toBe("15/01/2026");
    expect(formatDate(null)).toBe("—");
    expect(formatDate("pas-une-date")).toBe("pas-une-date");
  });

  test("formatDateTime", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("pas-une-date")).toBe("pas-une-date");
    expect(formatDateTime("2026-01-15T10:30:00")).toContain("15/01/2026");
    expect(formatDateTime("2026-01-15T10:30:00")).toContain("10:30");
  });

  test("formatScore", () => {
    expect(formatScore(0.925)).toBe("93 %");
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
  });

  test("formatDelta", () => {
    expect(formatDelta(0.05)).toBe("+5.0 %");
    expect(formatDelta(-0.1)).toBe("−10.0 %");
    expect(formatDelta(null)).toBe("—");
    expect(formatDelta(undefined)).toBe("—");
    expect(formatDelta(0)).toBe("0.0 %");
  });

  test("toNumber", () => {
    expect(toNumber("120.50")).toBe(120.5);
    expect(toNumber(7)).toBe(7);
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber("")).toBeNull();
    expect(toNumber("abc")).toBeNull();
  });
});
