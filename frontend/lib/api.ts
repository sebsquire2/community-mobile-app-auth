import { ApiCommunity, ApiUser } from './types';
import { invalidateSession } from './sessionInvalidation';
import {
  loadPersistedSession,
  loadSessionUserId,
  savePersistedSession,
  type PersistedSession,
} from './sessionStore';

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export class SessionExpiredError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'SessionExpiredError';
  }
}

type AuthResponse = {
  user: ApiUser;
  access_token: string;
  refresh_token: string;
  token_type: string;
};

// Access token lives in memory only — never written to persistent storage.
// On app restart it is recovered by hitting /auth/refresh with the persisted
// refresh token (which lives in the device keychain via expo-secure-store).
let accessToken: string | null = null;

// Mutex: at most one in-flight /auth/refresh call at any time.
// Without this, a burst of concurrent 401s would each independently call
// /auth/refresh, but the second call would present a now-revoked token
// (because the first call already rotated it) and cause a cascade of failures.
let refreshPromise: Promise<string | null> | null = null;

async function getStoredSession(): Promise<PersistedSession | null> {
  return loadPersistedSession();
}

async function updateStoredTokens(tokens: {
  accessToken: string;
  refreshToken: string;
  tokenType?: string;
}): Promise<void> {
  const session = await getStoredSession();
  if (!session?.user) return;
  await savePersistedSession({
    ...session,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken,
    tokenType: tokens.tokenType ?? session.tokenType ?? 'bearer',
  });
  accessToken = tokens.accessToken;
}

async function getRefreshToken(): Promise<string | null> {
  const session = await getStoredSession();
  return session?.refreshToken ?? null;
}

function shouldUseAuth(path: string) {
  return (
    !path.startsWith('/auth/login') &&
    !path.startsWith('/auth/register') &&
    !path.startsWith('/auth/refresh') &&
    !path.startsWith('/auth/google') &&
    !path.startsWith('/auth/apple') &&
    !path.startsWith('/health')
  );
}

async function loadAccessTokenFromStorage(): Promise<string | null> {
  if (accessToken) return accessToken;
  const session = await getStoredSession();
  accessToken = session?.accessToken ?? null;
  return accessToken;
}

async function doRefresh(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    invalidateSession();
    return null;
  }
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    invalidateSession();
    return null;
  }
  const payload = (await response.json()) as {
    access_token: string;
    refresh_token: string;
    token_type: string;
  };
  await updateStoredTokens({
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    tokenType: payload.token_type,
  });
  return payload.access_token;
}

async function getValidAccessToken(): Promise<string | null> {
  const existing = await loadAccessTokenFromStorage();
  if (existing) return existing;
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function requestWithAuth(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(options.headers ?? {});
  if (shouldUseAuth(path)) {
    const token = await getValidAccessToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (response.status === 401 && shouldUseAuth(path) && retry) {
    accessToken = null;
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (!refreshed) {
      return response;
    }
    return requestWithAuth(path, options, false);
  }
  return response;
}

async function handleResponseError(path: string, response: Response): Promise<never> {
  const message = await response.text();
  if (response.status === 401) {
    invalidateSession();
    throw new SessionExpiredError();
  }
  if (response.status === 404 && message.includes('User not found')) {
    const sessionUserId = await loadSessionUserId();
    if (sessionUserId && path.includes(sessionUserId)) {
      invalidateSession();
    }
  }
  throw new Error(message || `Request failed: ${response.status}`);
}

async function fetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (!headers.has('Content-Type') && options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await requestWithAuth(path, { ...options, headers });
  if (!response.ok) {
    await handleResponseError(path, response);
  }
  return (await response.json()) as T;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await fetchJson<AuthResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  accessToken = response.access_token;
  return response;
}

export async function loginWithGoogle(idToken: string): Promise<AuthResponse> {
  const response = await fetchJson<AuthResponse>('/auth/google', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken }),
  });
  accessToken = response.access_token;
  return response;
}

export async function loginWithApple(idToken: string, displayName?: string): Promise<AuthResponse> {
  const response = await fetchJson<AuthResponse>('/auth/apple', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken, display_name: displayName ?? null }),
  });
  accessToken = response.access_token;
  return response;
}

export async function register(payload: {
  email: string;
  password: string;
  displayName: string;
  communityId: string;
}): Promise<AuthResponse> {
  const response = await fetchJson<AuthResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  accessToken = response.access_token;
  return response;
}

export async function fetchMe(): Promise<ApiUser> {
  return fetchJson<ApiUser>('/users/me');
}

export async function fetchCommunities(): Promise<ApiCommunity[]> {
  return fetchJson<ApiCommunity[]>('/communities');
}

export async function fetchCommunityMembers(communityId: string): Promise<ApiUser[]> {
  return fetchJson<ApiUser[]>(`/communities/${encodeURIComponent(communityId)}/members`);
}

export async function updateMe(payload: { communityId?: string; displayName?: string }): Promise<ApiUser> {
  return fetchJson<ApiUser>('/users/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function logoutSession(): Promise<void> {
  const session = await getStoredSession();
  accessToken = null;
  refreshPromise = null;
  if (!session?.refreshToken) return;
  try {
    await requestWithAuth('/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
  } catch {
    // Ignore logout failures — clearing local session is the critical step.
  }
}
