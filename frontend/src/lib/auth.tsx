"use client";

/**
 * Contexte d'authentification.
 *
 * Fournit l'utilisateur courant, la connexion, la déconnexion et l'état de
 * chargement initial. Les jetons et le profil sont persistés dans le
 * `localStorage` ; le profil est rechargé depuis `/auth/me` au démarrage.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "@/lib/api-client";
import { ApiError } from "@/lib/errors";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getStoredUser,
  setTokens,
  storeUser,
} from "@/lib/tokens";
import type { User } from "@/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      const storedUser = getStoredUser<User>();
      if (!getAccessToken()) {
        setLoading(false);
        return;
      }
      try {
        const current = await api.me();
        if (!cancelled) {
          setUser(current);
          storeUser(current);
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          clearTokens();
        }
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const pair = await api.login(username, password);
    setTokens(pair.access_token, pair.refresh_token);
    const current = await api.me();
    setUser(current);
    storeUser(current);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      await api.logout(refreshToken);
    }
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth doit être utilisé dans un <AuthProvider>.");
  }
  return context;
}
