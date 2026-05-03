import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useSession } from '../lib/session';

export default function HomeScreen() {
  const { user, logout } = useSession();

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Welcome, {user?.displayName}</Text>
      <Text style={styles.sub}>@{user?.username}</Text>
      {user?.communityId && (
        <Text style={styles.community}>Community: {user.communityId}</Text>
      )}
      <TouchableOpacity style={styles.button} onPress={logout}>
        <Text style={styles.buttonText}>Sign out</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12, padding: 24 },
  heading: { fontSize: 22, fontWeight: '700' },
  sub: { fontSize: 15, color: '#666' },
  community: { fontSize: 14, color: '#999' },
  button: { marginTop: 24, backgroundColor: '#000', borderRadius: 10, paddingHorizontal: 24, paddingVertical: 12 },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 15 },
});
