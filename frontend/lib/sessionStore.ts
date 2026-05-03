import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { ApiUser } from './types';

let SecureStore: typeof import('expo-secure-store') | null = null;
if (Platform.OS !== 'web') {
  SecureStore = require('expo-secure-store');
}

export const SESSION_KEY = 'community-auth:session';
const REFRESH_TOKEN_SECURE_KEY = 'community-auth.refresh_token';

export type PersistedSession = {
  user: ApiUser;
  accessToken?: string;
  refreshToken?: string;
  tokenType?: string;
};

async function readRefreshTokenFromSecureStore(): Promise<string | null> {
  if (Platform.OS === 'web') {
    return localStorage.getItem(REFRESH_TOKEN_SECURE_KEY);
  }
  try {
    return await SecureStore!.getItemAsync(REFRESH_TOKEN_SECURE_KEY);
  } catch (error) {
    console.warn('Failed to read refresh token from SecureStore. Clearing key and continuing signed-out.', error);
    await SecureStore!.deleteItemAsync(REFRESH_TOKEN_SECURE_KEY).catch(() => {});
    return null;
  }
}

async function writeRefreshTokenToSecureStore(refreshToken: string): Promise<void> {
  if (Platform.OS === 'web') {
    localStorage.setItem(REFRESH_TOKEN_SECURE_KEY, refreshToken);
    return;
  }
  try {
    await SecureStore!.setItemAsync(REFRESH_TOKEN_SECURE_KEY, refreshToken);
    return;
  } catch (error) {
    console.warn('Failed to save refresh token to SecureStore. Retrying after deleting key.', error);
  }
  await SecureStore!.deleteItemAsync(REFRESH_TOKEN_SECURE_KEY).catch(() => {});
  await SecureStore!.setItemAsync(REFRESH_TOKEN_SECURE_KEY, refreshToken);
}

export async function loadPersistedSession(): Promise<PersistedSession | null> {
  const raw = await AsyncStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PersistedSession;
    // Access token is never persisted to disk; only the refresh token is.
    const { accessToken: _legacyAccessToken, ...parsedWithoutAccessToken } = parsed;
    const secureRefreshToken = await readRefreshTokenFromSecureStore();
    return { ...parsedWithoutAccessToken, refreshToken: secureRefreshToken ?? undefined };
  } catch {
    return null;
  }
}

export async function savePersistedSession(session: PersistedSession): Promise<void> {
  if (session.refreshToken) {
    await writeRefreshTokenToSecureStore(session.refreshToken);
  }
  // Only user metadata goes to AsyncStorage. Access token stays in memory only.
  // Refresh token lives in SecureStore (hardware-backed encrypted storage on iOS/Android).
  const { refreshToken: _rt, accessToken: _at, ...rest } = session;
  await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(rest));
}

export async function clearPersistedSession(): Promise<void> {
  await AsyncStorage.removeItem(SESSION_KEY);
  if (Platform.OS === 'web') {
    localStorage.removeItem(REFRESH_TOKEN_SECURE_KEY);
  } else {
    await SecureStore!.deleteItemAsync(REFRESH_TOKEN_SECURE_KEY).catch((error) => {
      console.warn('Failed to delete refresh token from SecureStore.', error);
    });
  }
}

export async function loadSessionUserId(): Promise<string | null> {
  const session = await loadPersistedSession();
  return session?.user?.id ?? null;
}
