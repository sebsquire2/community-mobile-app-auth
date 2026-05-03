import { Stack, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { Platform, View, StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession } from '../lib/session';

function AuthGate() {
  const router = useRouter();
  const segments = useSegments();
  const { user, isLoading } = useSession();

  useEffect(() => {
    if (isLoading) return;
    const onLogin = segments[0] === 'login';

    if (!user) {
      if (!onLogin) router.replace('/login');
      return;
    }

    if (onLogin) {
      router.replace('/');
    }
  }, [isLoading, router, segments, user]);

  return null;
}

function AppContent() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <AuthGate />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="login" />
          <Stack.Screen name="index" />
        </Stack>
      </SessionProvider>
    </SafeAreaProvider>
  );
}

export default function RootLayout() {
  if (Platform.OS === 'web') {
    return (
      <View style={styles.webContainer}>
        <View style={styles.phoneFrame}>
          <AppContent />
        </View>
      </View>
    );
  }
  return <AppContent />;
}

const styles = StyleSheet.create({
  webContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#111',
  },
  phoneFrame: {
    width: 390,
    height: 844,
    overflow: 'hidden',
    borderRadius: 20,
    backgroundColor: '#000',
  },
});
