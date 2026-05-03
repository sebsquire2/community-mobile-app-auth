import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useSession } from '../lib/session';
import { fetchCommunities, fetchCommunityMembers, updateMe } from '../lib/api';
import { ApiCommunity, ApiUser } from '../lib/types';

// Mock posts are community-themed so it's obvious why visibility matters.
const COMMUNITY_POSTS: Record<string, string[]> = {
  'community-runners': [
    "Just hit a new PB — 5k in 23:15 🏃",
    "Anyone joining the Saturday morning run?",
    "New trail route ready. Who's in?",
    "Recovery day. Foam rolling and coffee ☕",
    "Week 3 of marathon training done 💪",
    "Rain won't stop us! See you at 7am.",
  ],
  'community-books': [
    "Finished the Dostoevsky — three weeks but worth it.",
    "Chapter 8 discussion — did anyone see that ending coming?",
    "Next month's pick: recommendations welcome.",
    "Found a first edition at a charity shop 👀",
    "The audiobook narrator made all the difference.",
    "Re-reading it already. Didn't catch half of it first time.",
  ],
  'community-default': [
    "Hey everyone, good to be here.",
    "Anyone else trying the new features?",
    "Long weekend plans?",
    "Just joined — loving it so far.",
    "Happy Friday! 🎉",
    "Does anyone know how to switch community?",
  ],
};

const FALLBACK_POSTS = [
  "Excited to be part of this community!",
  "Looking forward to connecting with everyone.",
  "Great to meet you all.",
];

function mockPost(user: ApiUser, communityId: string | null, index: number): string {
  const pool = COMMUNITY_POSTS[communityId ?? ''] ?? FALLBACK_POSTS;
  // Use index so different members get different posts, not the same one.
  return pool[index % pool.length];
}

function initials(name: string): string {
  return name
    .split(' ')
    .map(w => w[0] ?? '')
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function Avatar({ name, size = 40, self = false }: { name: string; size?: number; self?: boolean }) {
  return (
    <View style={[
      styles.avatar,
      { width: size, height: size, borderRadius: size / 2 },
      self && styles.avatarSelf,
    ]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.36 }, self && styles.avatarTextSelf]}>
        {initials(name)}
      </Text>
    </View>
  );
}

function PostCard({ member, communityId, index, isSelf }: {
  member: ApiUser;
  communityId: string | null;
  index: number;
  isSelf: boolean;
}) {
  const likes = ((member.id.charCodeAt(5) ?? 7) % 20) + 1;
  const comments = ((member.id.charCodeAt(6) ?? 3) % 8);

  return (
    <View style={[styles.postCard, isSelf && styles.postCardSelf]}>
      <View style={styles.postHeader}>
        <Avatar name={member.displayName} self={isSelf} />
        <View style={styles.postHeaderText}>
          <Text style={styles.postName}>
            {member.displayName}
            {isSelf && <Text style={styles.youBadge}> · you</Text>}
          </Text>
          <Text style={styles.postUsername}>@{member.username}</Text>
        </View>
      </View>
      <Text style={styles.postBody}>{mockPost(member, communityId, index)}</Text>
      <Text style={styles.postMeta}>❤️ {likes}  💬 {comments}</Text>
    </View>
  );
}

function LockedCommunity({ community }: { community: ApiCommunity }) {
  return (
    <View style={styles.lockedCard}>
      <View style={styles.lockedHeader}>
        <Text style={styles.lockIcon}>🔒</Text>
        <View>
          <Text style={styles.lockedName}>{community.name}</Text>
          <Text style={styles.lockedCount}>
            {community.memberCount} {community.memberCount === 1 ? 'member' : 'members'}
          </Text>
        </View>
      </View>
      <Text style={styles.lockedMsg}>Posts from this community are only visible to its members.</Text>
    </View>
  );
}

function CommunityPicker({
  communities,
  currentId,
  onPick,
  onCancel,
  loading,
}: {
  communities: ApiCommunity[];
  currentId: string | null;
  onPick: (id: string) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  return (
    <View style={styles.pickerOverlay}>
      <Text style={styles.pickerTitle}>Switch community</Text>
      <Text style={styles.pickerSub}>You'll see posts from members of the new community.</Text>
      {communities.map(c => (
        <TouchableOpacity
          key={c.id}
          style={[styles.pickerCard, c.id === currentId && styles.pickerCardCurrent]}
          onPress={() => c.id !== currentId && onPick(c.id)}
          disabled={loading || c.id === currentId}
        >
          <Text style={[styles.pickerCardName, c.id === currentId && styles.pickerCardNameCurrent]}>
            {c.name}
          </Text>
          <Text style={[styles.pickerCardCount, c.id === currentId && styles.pickerCardCountCurrent]}>
            {c.id === currentId ? 'current' : `${c.memberCount} members`}
          </Text>
        </TouchableOpacity>
      ))}
      {loading && <ActivityIndicator style={{ marginTop: 8 }} />}
      <TouchableOpacity onPress={onCancel} disabled={loading}>
        <Text style={styles.pickerCancel}>Cancel</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function HomeScreen() {
  const { user, logout, updateUser } = useSession();

  const [members, setMembers] = useState<ApiUser[]>([]);
  const [communities, setCommunities] = useState<ApiCommunity[]>([]);
  const [loadingFeed, setLoadingFeed] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [switchLoading, setSwitchLoading] = useState(false);

  const loadFeed = useCallback((communityId: string) => {
    setLoadingFeed(true);
    fetchCommunityMembers(communityId)
      .then(setMembers)
      .catch(() => {})
      .finally(() => setLoadingFeed(false));
  }, []);

  useEffect(() => {
    fetchCommunities().then(setCommunities).catch(() => {});
  }, []);

  useEffect(() => {
    if (user?.communityId) loadFeed(user.communityId);
  }, [user?.communityId, loadFeed]);

  const handleSwitch = async (communityId: string) => {
    setSwitchLoading(true);
    try {
      const updated = await updateMe({ communityId });
      await updateUser(updated);
      setShowPicker(false);
    } catch {
      // leave picker open so user can retry
    } finally {
      setSwitchLoading(false);
    }
  };

  const currentCommunity = communities.find(c => c.id === user?.communityId);
  const otherCommunities = communities.filter(c => c.id !== user?.communityId);

  if (!user) return null;

  if (showPicker) {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <CommunityPicker
          communities={communities}
          currentId={user.communityId}
          onPick={handleSwitch}
          onCancel={() => setShowPicker(false)}
          loading={switchLoading}
        />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.communityName}>
            {currentCommunity?.name ?? 'No community'}
          </Text>
          <Text style={styles.communityMeta}>
            {currentCommunity
              ? `${currentCommunity.memberCount} members · your community`
              : 'You haven\'t joined a community yet'}
          </Text>
        </View>
        <Avatar name={user.displayName} size={36} self />
      </View>

      {/* Community feed */}
      {loadingFeed ? (
        <ActivityIndicator style={styles.loader} />
      ) : members.length > 0 ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Community feed</Text>
          {members.map((m, i) => (
            <PostCard
              key={m.id}
              member={m}
              communityId={user.communityId}
              index={i}
              isSelf={m.id === user.id}
            />
          ))}
        </View>
      ) : (
        <Text style={styles.emptyFeed}>No members in your community yet.</Text>
      )}

      {/* Locked communities */}
      {otherCommunities.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Other communities</Text>
          {otherCommunities.map(c => (
            <LockedCommunity key={c.id} community={c} />
          ))}
        </View>
      )}

      {/* Actions */}
      <View style={styles.actions}>
        <TouchableOpacity style={styles.switchButton} onPress={() => setShowPicker(true)}>
          <Text style={styles.switchButtonText}>Switch community</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.signOutButton} onPress={logout}>
          <Text style={styles.signOutText}>Sign out</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { padding: 20, gap: 24, paddingBottom: 40 },

  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  communityName: { fontSize: 22, fontWeight: '700', letterSpacing: -0.4 },
  communityMeta: { fontSize: 13, color: '#888', marginTop: 2 },

  avatar: { backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  avatarSelf: { backgroundColor: '#222' },
  avatarText: { color: '#fff', fontWeight: '700' },
  avatarTextSelf: { color: '#fff' },

  loader: { marginTop: 40 },
  emptyFeed: { fontSize: 14, color: '#999', textAlign: 'center', marginTop: 16 },

  section: { gap: 12 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#999', textTransform: 'uppercase', letterSpacing: 0.8 },

  postCard: { borderWidth: 1, borderColor: '#eee', borderRadius: 12, padding: 14, gap: 10, backgroundColor: '#fff' },
  postCardSelf: { borderColor: '#ddd', backgroundColor: '#fafafa' },
  postHeader: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  postHeaderText: { flex: 1 },
  postName: { fontSize: 14, fontWeight: '600', color: '#000' },
  youBadge: { fontWeight: '400', color: '#999' },
  postUsername: { fontSize: 12, color: '#aaa' },
  postBody: { fontSize: 14, color: '#222', lineHeight: 20 },
  postMeta: { fontSize: 12, color: '#bbb' },

  lockedCard: { borderWidth: 1, borderColor: '#eee', borderRadius: 12, padding: 14, gap: 8, backgroundColor: '#fafafa' },
  lockedHeader: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  lockIcon: { fontSize: 18 },
  lockedName: { fontSize: 14, fontWeight: '600', color: '#555' },
  lockedCount: { fontSize: 12, color: '#aaa' },
  lockedMsg: { fontSize: 13, color: '#bbb', fontStyle: 'italic' },

  actions: { gap: 10, marginTop: 8 },
  switchButton: { borderWidth: 1, borderColor: '#000', borderRadius: 10, padding: 13, alignItems: 'center' },
  switchButtonText: { fontSize: 15, fontWeight: '600', color: '#000' },
  signOutButton: { borderWidth: 1, borderColor: '#ddd', borderRadius: 10, padding: 13, alignItems: 'center' },
  signOutText: { fontSize: 15, fontWeight: '500', color: '#888' },

  pickerOverlay: { gap: 14 },
  pickerTitle: { fontSize: 20, fontWeight: '700', letterSpacing: -0.3 },
  pickerSub: { fontSize: 14, color: '#666', marginTop: -6 },
  pickerCard: { borderWidth: 1, borderColor: '#ddd', borderRadius: 12, padding: 16, backgroundColor: '#fafafa' },
  pickerCardCurrent: { borderColor: '#000', backgroundColor: '#000' },
  pickerCardName: { fontSize: 16, fontWeight: '600', color: '#000' },
  pickerCardNameCurrent: { color: '#fff' },
  pickerCardCount: { fontSize: 13, color: '#888', marginTop: 2 },
  pickerCardCountCurrent: { color: '#ccc' },
  pickerCancel: { textAlign: 'center', fontSize: 14, color: '#555', paddingVertical: 4, marginTop: 4 },
});
