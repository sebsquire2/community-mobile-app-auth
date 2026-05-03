import { useEffect, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSession } from '../lib/session';
import { fetchCommunities } from '../lib/api';
import { ApiCommunity } from '../lib/types';

type Mode = 'login' | 'register' | 'pick-community';

export default function LoginScreen() {
  const router = useRouter();
  const { login, register } = useSession();

  const [mode, setMode] = useState<Mode>('login');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const [communities, setCommunities] = useState<ApiCommunity[]>([]);
  const [communitiesLoading, setCommunitiesLoading] = useState(false);
  const [selectedCommunity, setSelectedCommunity] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);

    if (mode === 'login') {
      setIsLoading(true);
      try {
        await login(email.trim().toLowerCase(), password);
        router.replace('/');
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes('401') || message.includes('Invalid credentials')) {
          setError('Incorrect email or password.');
        } else if (message.includes('429') || message.includes('Too many')) {
          setError('Too many attempts. Please wait and try again.');
        } else if (message.includes('uses') && message.includes('sign-in')) {
          setError(message);
        } else {
          setError(message || 'Login failed.');
        }
      } finally {
        setIsLoading(false);
      }
      return;
    }

    if (mode === 'register') {
      if (!displayName.trim()) { setError('Display name is required.'); return; }
      if (!email.trim()) { setError('Email is required.'); return; }
      if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }

      setCommunitiesLoading(true);
      setError(null);
      try {
        const list = await fetchCommunities();
        setCommunities(list);
        setMode('pick-community');
      } catch {
        setError('Could not load communities. Check your connection.');
      } finally {
        setCommunitiesLoading(false);
      }
      return;
    }

    if (mode === 'pick-community') {
      if (!selectedCommunity) { setError('Please pick a community to continue.'); return; }
      setIsLoading(true);
      try {
        await register(displayName.trim(), email.trim().toLowerCase(), password, selectedCommunity);
        router.replace('/');
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes('409') || message.includes('already registered')) {
          setError('That email is already registered.');
          setMode('register');
        } else if (message.includes('8 characters')) {
          setError('Password must be at least 8 characters.');
          setMode('register');
        } else if (message.includes('Invalid email')) {
          setError('Please enter a valid email address.');
          setMode('register');
        } else {
          setError(message || 'Registration failed.');
        }
      } finally {
        setIsLoading(false);
      }
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setDisplayName('');
    setEmail('');
    setPassword('');
    setSelectedCommunity(null);
  };

  const submitLabel = () => {
    if (isLoading || communitiesLoading) {
      if (mode === 'login') return 'Signing in…';
      if (mode === 'register') return 'Loading communities…';
      return 'Creating account…';
    }
    if (mode === 'login') return 'Sign in';
    if (mode === 'register') return 'Next: pick a community';
    return 'Create account';
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }} keyboardShouldPersistTaps="handled">
        <View style={styles.container}>
          <Text style={styles.title}>Community</Text>

          {mode !== 'pick-community' && (
            <View style={styles.tabRow}>
              <TouchableOpacity style={[styles.tab, mode === 'login' && styles.tabActive]} onPress={() => switchMode('login')}>
                <Text style={[styles.tabText, mode === 'login' && styles.tabTextActive]}>Sign in</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.tab, mode === 'register' && styles.tabActive]} onPress={() => switchMode('register')}>
                <Text style={[styles.tabText, mode === 'register' && styles.tabTextActive]}>Create account</Text>
              </TouchableOpacity>
            </View>
          )}

          {mode === 'pick-community' ? (
            <View style={styles.form}>
              <Text style={styles.pickHeading}>Pick your community</Text>
              <Text style={styles.pickSub}>You'll see posts from members of your community.</Text>

              {communities.map(c => (
                <TouchableOpacity
                  key={c.id}
                  style={[styles.communityCard, selectedCommunity === c.id && styles.communityCardSelected]}
                  onPress={() => setSelectedCommunity(c.id)}
                >
                  <Text style={[styles.communityName, selectedCommunity === c.id && styles.communityNameSelected]}>
                    {c.name}
                  </Text>
                  <Text style={[styles.communityCount, selectedCommunity === c.id && styles.communityCountSelected]}>
                    {c.memberCount} {c.memberCount === 1 ? 'member' : 'members'}
                  </Text>
                </TouchableOpacity>
              ))}

              {error ? <Text style={styles.error}>{error}</Text> : null}

              <TouchableOpacity
                style={[styles.button, (!selectedCommunity || isLoading) && styles.buttonDisabled]}
                onPress={handleSubmit}
                disabled={!selectedCommunity || isLoading}
              >
                <Text style={styles.buttonText}>{isLoading ? 'Creating account…' : 'Create account'}</Text>
              </TouchableOpacity>

              <TouchableOpacity onPress={() => { setMode('register'); setError(null); }}>
                <Text style={styles.backLink}>← Back</Text>
              </TouchableOpacity>
            </View>
          ) : (
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

              <TouchableOpacity
                style={[styles.button, (isLoading || communitiesLoading) && styles.buttonDisabled]}
                onPress={handleSubmit}
                disabled={isLoading || communitiesLoading}
              >
                <Text style={styles.buttonText}>{submitLabel()}</Text>
              </TouchableOpacity>
            </View>
          )}
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
  pickHeading: { fontSize: 20, fontWeight: '700', letterSpacing: -0.3 },
  pickSub: { fontSize: 14, color: '#666', marginTop: -8 },
  communityCard: { borderWidth: 1, borderColor: '#ddd', borderRadius: 12, padding: 16, backgroundColor: '#fafafa' },
  communityCardSelected: { borderColor: '#000', backgroundColor: '#000' },
  communityName: { fontSize: 16, fontWeight: '600', color: '#000' },
  communityNameSelected: { color: '#fff' },
  communityCount: { fontSize: 13, color: '#888', marginTop: 2 },
  communityCountSelected: { color: '#ccc' },
  backLink: { textAlign: 'center', fontSize: 14, color: '#555', paddingVertical: 4 },
});
