/** Tests de la gestion des jetons et du profil en `localStorage`. */

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getStoredUser,
  setTokens,
  storeUser,
} from "@/lib/tokens";

describe("tokens", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test("setTokens et getAccessToken / getRefreshToken", () => {
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();

    setTokens("access-1", "refresh-1");

    expect(getAccessToken()).toBe("access-1");
    expect(getRefreshToken()).toBe("refresh-1");
  });

  test("clearTokens retire les jetons et le profil", () => {
    setTokens("access-1", "refresh-1");
    storeUser({ id: 1 });

    clearTokens();

    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  test("storeUser null supprime le profil", () => {
    storeUser({ id: 1 });
    expect(getStoredUser()).toEqual({ id: 1 });

    storeUser(null);
    expect(getStoredUser()).toBeNull();
  });

  test("getStoredUser gère l'absence et le JSON invalide", () => {
    expect(getStoredUser()).toBeNull();

    window.localStorage.setItem("si_user", "{invalide");
    expect(getStoredUser()).toBeNull();

    window.localStorage.setItem("si_user", "{\"id\": 2}");
    expect(getStoredUser()).toEqual({ id: 2 });
  });
});
