/** Tests de la configuration de l'application. */

import { API_BASE_URL, PAGE_SIZE } from "@/lib/config";

describe("config", () => {
  test("expose une URL de base d'API par défaut", () => {
    expect(typeof API_BASE_URL).toBe("string");
  });

  test("définit la taille de page", () => {
    expect(PAGE_SIZE).toBe(20);
  });
});
