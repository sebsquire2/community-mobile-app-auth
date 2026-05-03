import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GoogleSignin, statusCodes } from '@react-native-google-signin/google-signin';
import * as AppleAuthentication from 'expo-apple-authentication';
import { useSession } from '../lib/session';

GoogleSignin.configure({
  webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,
  iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID,
});

type Mode = 'login' | 'register';

export default function LoginScreen() {
  const router = useRouter();
  const { login, loginWithGoogle, loginWithApple, register } = useSession();

  const [mode, setMode] = useState<Mode>('login');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleOAuth = async (fn: () => Promise<void>) => {
    setError(null);
    setIsLoading(true);
    try {
      await fn();
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      await GoogleSignin.hasPlayServices();
      const userInfo = await GoogleSignin.signIn();
      const idToken = userInfo.data?.idToken;
      if (!idToken) {
        setError('Google sign in failed — no ID token returned.');
        return;
      }
      await handleOAuth(() => loginWithGoogle(idToken));
    } catch (e: unknown) {
      const err = e as { code?: string };
      if (err.code === statusCodes.SIGN_IN_CANCELLED) return;
      if (err.code === statusCodes.IN_PROGRESS) return;
      setError('Google sign in failed.');
    }
  };

  const handleAppleLogin = async () => {
    try {
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!credential.identityToken) {
        setError('Apple sign in failed.');
        return;
      }
      const name = credential.fullName
        ? [credential.fullName.givenName, credential.fullName.familyName].filter(Boolean).join(' ')
        : undefined;
      await handleOAuth(() => loginWithApple(credential.identityToken!, name || undefined));
    } catch (e: unknown) {
      if ((e as { code?: string }).code === 'ERR_CANCELED') return;
      setError('Apple sign in failed.');
    }
  };

  const handleSubmit = async () => {
    setError(null);
    setIsLoading(true);
    try {
      if (mode === 'login') {
        await login(email.trim().toLowerCase(), password);
      } else {
        if (!displayName.trim()) {
          setError('Display name is required.');
          return;
        }
        await register(displayName.trim(), email.trim().toLowerCase(), password);
      }
      router.replace('/');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes('409') || message.includes('already registered')) {
        setError('That email is already registered.');
      } else if (message.includes('401') || message.includes('Invalid credentials')) {
        setError('Incorrect email or password.');
      } else if (message.includes('429') || message.includes('Too many')) {
        setError('Too many attempts. Please wait and try again.');
      } else if (message.includes('8 characters')) {
        setError('Password must be at least 8 characters.');
      } else if (message.includes('Invalid email address')) {
        setError('Please enter a valid email address.');
      } else if (message.includes('Display name required')) {
        setError('Display name is required.');
      } else if (message.includes('uses') && message.includes('sign-in')) {
        setError(message);
      } else {
        setError(message || (mode === 'login' ? 'Login failed.' : 'Registration failed.'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setDisplayName('');
    setEmail('');
    setPassword('');
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }} keyboardShouldPersistTaps="handled">
        <View style={styles.container}>
          <Text style={styles.title}>Community</Text>

          <View style={styles.tabRow}>
            <TouchableOpacity style={[styles.tab, mode === 'login' && styles.tabActive]} onPress={() => switchMode('login')}>
              <Text style={[styles.tabText, mode === 'login' && styles.tabTextActive]}>Sign in</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.tab, mode === 'register' && styles.tabActive]} onPress={() => switchMode('register')}>
              <Text style={[styles.tabText, mode === 'register' && styles.tabTextActive]}>Create account</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.form}>
            {mode === 'register' && (
              <View style={styles.field}>
                <Text style={styles.label}>Display name</Text>
                <TextInput
                  value={displayName}
                  onChangeText={setDisplayName}
                  placeholder="Your name"
                  autoCapitalize="words"
                  style={styles.input}
                />
              </View>
            )}

            <View style={styles.field}>
              <Text style={styles.label}>Email</Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                autoCapitalize="none"
                keyboardType="email-address"
                autoComplete="email"
                style={styles.input}
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Password</Text>
              <View style={styles.passwordRow}>
                <TextInput
                  value={password}
                  onChangeText={setPassword}
                  placeholder={mode === 'register' ? 'At least 8 characters' : ''}
                  secureTextEntry={!showPassword}
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                  style={[styles.input, styles.passwordInput]}
                />
                <TouchableOpacity onPress={() => setShowPassword(v => !v)} style={styles.eyeButton}>
                  <Text style={styles.eyeText}>{showPassword ? 'Hide' : 'Show'}</Text>
                </TouchableOpacity>
              </View>
            </View>

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <TouchableOpacity style={[styles.button, isLoading && styles.buttonDisabled]} onPress={handleSubmit} disabled={isLoading}>
              <Text style={styles.buttonText}>
                {isLoading
                  ? mode === 'login' ? 'Signing in…' : 'Creating account…'
                  : mode === 'login' ? 'Sign in' : 'Create account'}
              </Text>
            </TouchableOpacity>
          </View>

          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          <View style={styles.socialButtons}>
            <TouchableOpacity style={[styles.socialButton, isLoading && styles.buttonDisabled]} onPress={handleGoogleLogin} disabled={isLoading}>
              <Text style={styles.socialButtonText}>Continue with Google</Text>
            </TouchableOpacity>

            {Platform.OS === 'ios' && (
              <TouchableOpacity style={[styles.socialButton, styles.appleButton, isLoading && styles.buttonDisabled]} onPress={handleAppleLogin} disabled={isLoading}>
                <Text style={[styles.socialButtonText, styles.appleButtonText]}>Continue with Apple</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { gap: 24, paddingHorizontal: 24, paddingVertical: 40 },
  title: { fontSize: 28, fontWeight: '700', textAlign: 'center', letterSpacing: -0.5 },
  tabRow: { flexDirection: 'row', borderRadius: 10, backgroundColor: '#f0f0f0', padding: 4 },
  tab: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  tabActive: { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, shadowOffset: { width: 0, height: 1 }, elevation: 2 },
  tabText: { fontSize: 14, fontWeight: '500', color: '#888' },
  tabTextActive: { color: '#000', fontWeight: '600' },
  form: { gap: 16 },
  field: { gap: 6 },
  label: { fontSize: 14, fontWeight: '600', color: '#333' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 12, fontSize: 15, backgroundColor: '#fafafa' },
  passwordRow: { flexDirection: 'row', alignItems: 'center' },
  passwordInput: { flex: 1, borderTopRightRadius: 0, borderBottomRightRadius: 0, borderRightWidth: 0 },
  eyeButton: { borderWidth: 1, borderColor: '#ddd', borderTopRightRadius: 10, borderBottomRightRadius: 10, backgroundColor: '#fafafa', paddingHorizontal: 12, paddingVertical: 13 },
  eyeText: { fontSize: 13, color: '#555', fontWeight: '500' },
  error: { color: '#b00020', fontSize: 14 },
  button: { backgroundColor: '#000', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 4 },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 15 },
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  dividerLine: { flex: 1, height: 1, backgroundColor: '#e0e0e0' },
  dividerText: { fontSize: 13, color: '#999' },
  socialButtons: { gap: 12 },
  socialButton: { borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 14, alignItems: 'center', backgroundColor: '#fff' },
  socialButtonText: { fontSize: 15, fontWeight: '600', color: '#000' },
  appleButton: { backgroundColor: '#000', borderColor: '#000' },
  appleButtonText: { color: '#fff' },
});
