/** Tests de la normalisation des erreurs API. */

import { ApiError, extractDetail } from "@/lib/errors";

describe("errors", () => {
  test("ApiError porte status et detail", () => {
    const error = new ApiError(409, "Doublon détecté.");

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(409);
    expect(error.detail).toBe("Doublon détecté.");
    expect(error.message).toBe("Doublon détecté.");
  });

  test("extractDetail lit une chaîne detail", () => {
    expect(extractDetail({ detail: "Fichier invalide" })).toBe("Fichier invalide");
  });

  test("extractDetail concatène les erreurs de validation FastAPI", () => {
    const data = {
      detail: [
        { msg: "Champ requis" },
        { msg: "Valeur invalide" },
        { loc: ["x"] },
      ],
    };
    expect(extractDetail(data)).toBe("Champ requis ; Valeur invalide ; Champ invalide");
  });

  test("extractDetail sérialise un detail non-string", () => {
    expect(extractDetail({ detail: { code: "X" } })).toBe('{"code":"X"}');
  });

  test("extractDetail sans detail renvoie un message générique", () => {
    expect(extractDetail({ error: "boom" })).toBe("Une erreur inattendue est survenue.");
    expect(extractDetail(null)).toBe("Une erreur inattendue est survenue.");
    expect(extractDetail("texte brut")).toBe("Une erreur inattendue est survenue.");
  });
});
