/** Gestion des jetons d'authentification et du profil en `localStorage`. */

const ACCESS_KEY = "si_access_token";
const REFRESH_KEY = "si_refresh_token";
const USER_KEY = "si_user";

export function getAccessToken(): string | null {
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  window.localStorage.setItem(ACCESS_KEY, accessToken);
  window.localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function getStoredUser<T>(): T | null {
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function storeUser<T>(user: T | null): void {
  if (user === null) {
    window.localStorage.removeItem(USER_KEY);
  } else {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}
