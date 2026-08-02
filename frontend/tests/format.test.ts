/** Tests des utilitaires de formatage. */

import { formatCurrency, formatDate, formatDelta, formatScore } from "@/lib/format";

describe("format", () => {
  test("formatCurrency", () => {
    const formatted = formatCurrency("120.00", "EUR");
    expect(formatted).toMatch(/120,00/);
    expect(formatted).toContain("€");
    expect(formatCurrency(null, "EUR")).toBe("—");
    expect(formatCurrency("", "EUR")).toBe("—");
  });

  test("formatDate", () => {
    expect(formatDate("2026-01-15")).toBe("15/01/2026");
    expect(formatDate(null)).toBe("—");
  });

  test("formatScore", () => {
    expect(formatScore(0.925)).toBe("93 %");
    expect(formatScore(null)).toBe("—");
  });

  test("formatDelta", () => {
    expect(formatDelta(0.05)).toBe("+5.0 %");
    expect(formatDelta(-0.1)).toBe("−10.0 %");
    expect(formatDelta(null)).toBe("—");
  });
});
