/** Tests des libellés et styles des statuts, sévérités, catégories et actions. */

import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  ROLE_LABELS,
  SEVERITY_STYLES,
  SORT_OPTIONS,
  STATUS_ORDER,
  STATUS_STYLES,
} from "@/lib/status";

describe("status", () => {
  test("STATUS_ORDER couvre tous les statuts de l'application", () => {
    expect(STATUS_ORDER).toEqual([
      "Déposée",
      "En cours d'analyse",
      "À vérifier",
      "Validée",
      "Vendor Bill créée",
      "Rejetée",
      "Erreur système",
    ]);
  });

  test("STATUS_STYLES définit un style pour chaque statut", () => {
    for (const status of STATUS_ORDER) {
      expect(STATUS_STYLES[status]).toMatch(/bg-|ring-/);
    }
    expect(STATUS_STYLES["Rejetée"]).toContain("rose");
    expect(STATUS_STYLES["Validée"]).toContain("emerald");
  });

  test("SEVERITY_STYLES couvre les trois sévérités", () => {
    expect(SEVERITY_STYLES.info).toContain("sky");
    expect(SEVERITY_STYLES.warning).toContain("amber");
    expect(SEVERITY_STYLES.critical).toContain("red");
  });

  test("CATEGORY_LABELS couvre toutes les catégories", () => {
    expect(CATEGORY_LABELS).toEqual({
      montant: "Montant",
      tva: "TVA",
      quantite: "Quantité",
      produit_absent: "Produit absent",
      doublon: "Doublon",
      fournisseur: "Fournisseur",
      bon_commande: "Bon de commande",
      autre: "Autre",
    });
  });

  test("ACTION_LABELS couvre les actions d'audit", () => {
    expect(ACTION_LABELS).toEqual({
      validation: "Validation",
      correction: "Correction",
      rejet: "Rejet",
      vendor_bill_créée: "Vendor Bill",
    });
  });

  test("ROLE_LABELS couvre les rôles", () => {
    expect(ROLE_LABELS).toEqual({
      Administrateur: "Administrateur",
      Comptable: "Comptable",
      Acheteur: "Acheteur",
    });
  });

  test("SORT_OPTIONS propose les quatre tris", () => {
    expect(SORT_OPTIONS.map((o) => o.value)).toEqual([
      "created_at_desc",
      "created_at_asc",
      "issue_date_desc",
      "issue_date_asc",
    ]);
  });
});
