/** Tests des tokens de style du design system. */

import { BADGE_BASE, BADGE_TONES } from "@/lib/design";
import { ROLE_TONES, SEVERITY_LABELS, STATUS_ORDER, STATUS_STYLES } from "@/lib/status";
import { Badge } from "@/components/ui/Badge";
import { render, screen } from "@testing-library/react";

test("BADGE_TONES couvre tous les tons utilisés par les badges", () => {
  expect(BADGE_TONES.slate).toContain("bg-slate-100");
  expect(BADGE_TONES.emerald).toContain("ring-emerald-300");
  expect(BADGE_TONES.rose).toContain("text-rose-700");
});

test("Badge applique le ton demandé sans duplication", () => {
  render(<Badge tone="emerald">Validée</Badge>);
  const badge = screen.getByText("Validée");
  expect(BADGE_TONES.emerald.split(" ").every((cls) => badge.classList.contains(cls))).toBe(true);
});

test("les styles de statut partagent la base pill", () => {
  for (const status of STATUS_ORDER) {
    const classes = STATUS_STYLES[status].split(" ");
    expect(classes.some((cls) => cls.startsWith("bg-"))).toBe(true);
    expect(classes.some((cls) => cls.startsWith("text-"))).toBe(true);
  }
  expect(BADGE_BASE).toContain("rounded-full");
});

test("les tons de rôle couvrent tous les rôles", () => {
  expect(ROLE_TONES["Administrateur"]).toBe("violet");
  expect(ROLE_TONES["Comptable"]).toBe("blue");
  expect(ROLE_TONES["Acheteur"]).toBe("emerald");
});

test("les libellés de sévérité sont définis", () => {
  expect(SEVERITY_LABELS.critical).toBe("Critique");
  expect(SEVERITY_LABELS.warning).toBe("Avertissement");
});