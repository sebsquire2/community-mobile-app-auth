import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ApiUser } from './types';
import {
  SessionExpiredError,
  fetchMe,
  login as apiLogin,
  logoutSession as apiLogoutSession,
  register as apiRegister,
} from './api';
import { invalidateSession, onSessionInvalidated } from './sessionInvalidation';
import { clearPersistedSession, loadPersistedSession, savePersistedSession } from './sessionStore';

type SessionState = {
  user: ApiUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (displayName: string, email: string, password: string, communityId: string) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (nextUser: ApiUser) => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const persistSession = useCallback(
    async (
      nextUser: ApiUser,
      tokens?: { accessToken: string; refreshToken: string; tokenType?: string }
    ) => {
      const existing = await loadPersistedSession();
      const nextSession = {
        user: nextUser,
        accessToken: tokens?.accessToken ?? existing?.accessToken,
        refreshToken: tokens?.refreshToken ?? existing?.refreshToken,
        tokenType: tokens?.tokenType ?? existing?.tokenType ?? 'bearer',
      };
      await savePersistedSession(nextSession);
      setUser(nextUser);
    },
    []
  );

  const clearSession = useCallback(async () => {
    setUser(null);
    await clearPersistedSession();
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { user: nextUser, access_token, refresh_token, token_type } = await apiLogin(email, password);
      await persistSession(nextUser, { accessToken: access_token, refreshToken: refresh_token, tokenType: token_type });
    },
    [persistSession]
  );

  const register = useCallback(
    async (displayName: string, email: string, password: string, communityId: string) => {
      const { user: nextUser, access_token, refresh_token, token_type } = await apiRegister({ displayName, email, password, communityId });
      await persistSession(nextUser, { accessToken: access_token, refreshToken: refresh_token, tokenType: token_type });
    },
    [persistSession]
  );

  const updateUser = useCallback(
    async (nextUser: ApiUser) => {
      await persistSession(nextUser);
    },
    [persistSession]
  );

  const logout = useCallback(async () => {
    await apiLogoutSession();
    await clearSession();
  }, [clearSession]);

  // On mount: restore session from storage and re-validate with the server.
  useEffect(() => {
    let isActive = true;

    const load = async () => {
      setIsLoading(true);
      try {
        const session = await loadPersistedSession();
        if (!session?.user) {
          if (isActive) setIsLoading(false);
          return;
        }
        if (!session.refreshToken) {
          await clearPersistedSession();
          if (isActive) setUser(null);
          return;
        }
        if (isActive) setUser(session.user);
        try {
          const freshUser = await fetchMe();
          if (isActive) await persistSession(freshUser);
        } catch {
          // Fall back to persisted user; token refresh handles invalid sessions elsewhere.
        }
      } catch {
        await clearPersistedSession();
      } finally {
        if (isActive) setIsLoading(false);
      }
    };

    load();
    return () => {
      isActive = false;
    };
  }, []);

  // Listen for session invalidation events fired by the API layer (e.g. 401 after
  // a failed refresh) and clear local session state.
  useEffect(() => {
    const unsubscribe = onSessionInvalidated(() => {
      void clearSession();
    });
    return () => unsubscribe();
  }, [clearSession]);

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout, updateUser }),
    [user, isLoading, login, register, logout, updateUser]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error('useSession must be used within SessionProvider');
  return context;
}
