import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useSession } from '../lib/session';
import {
  fetchCommunities,
  fetchCityFeed,
  fetchCommunityFeed,
  createPost,
  updateMe,
} from '../lib/api';
import { ApiCommunity, ApiPost } from '../lib/types';

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function initials(name: string) {
  return name.split(' ').map(w => w[0] ?? '').join('').toUpperCase().slice(0, 2);
}

function Avatar({ name, size = 36, highlight = false }: { name: string; size?: number; highlight?: boolean }) {
  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }, highlight && styles.avatarHighlight]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.38 }]}>{initials(name)}</Text>
    </View>
  );
}

function VisibilityBadge({ v }: { v: 'public' | 'community' }) {
  return (
    <View style={[styles.badge, v === 'community' && styles.badgeCommunity]}>
      <Text style={[styles.badgeText, v === 'community' && styles.badgeTextCommunity]}>
        {v === 'public' ? '🌍 Public' : '🏘️ Community'}
      </Text>
    </View>
  );
}

function PostCard({ post, isSelf }: { post: ApiPost; isSelf: boolean }) {
  return (
    <View style={[styles.postCard, isSelf && styles.postCardSelf]}>
      <View style={styles.postTop}>
        <Avatar name={post.author.displayName} highlight={isSelf} />
        <View style={{ flex: 1 }}>
          <View style={styles.postMeta}>
            <Text style={styles.postName}>
              {post.author.displayName}
              {isSelf ? <Text style={styles.selfTag}> · you</Text> : null}
            </Text>
            <VisibilityBadge v={post.visibility} />
          </View>
          <Text style={styles.postSub}>
            {post.communityName ?? 'No community'} · {timeAgo(post.createdAt)}
          </Text>
        </View>
      </View>
      <Text style={styles.postBody}>{post.body}</Text>
    </View>
  );
}

function PostComposer({
  communityName,
  onPost,
}: {
  communityName: string | null;
  onPost: (body: string, visibility: 'public' | 'community') => Promise<void>;
}) {
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState<'public' | 'community'>('public');
  const [posting, setPosting] = useState(false);

  const submit = async () => {
    if (!body.trim() || posting) return;
    setPosting(true);
    try {
      await onPost(body.trim(), visibility);
      setBody('');
    } finally {
      setPosting(false);
    }
  };

  return (
    <View style={styles.composer}>
      <TextInput
        value={body}
        onChangeText={setBody}
        placeholder="What's on your mind?"
        multiline
        style={styles.composerInput}
      />
      <View style={styles.composerRow}>
        <View style={styles.visibilityToggle}>
          <TouchableOpacity
            style={[styles.visToggleBtn, visibility === 'public' && styles.visToggleBtnActive]}
            onPress={() => setVisibility('public')}
          >
            <Text style={[styles.visToggleText, visibility === 'public' && styles.visToggleTextActive]}>
              🌍 Public
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.visToggleBtn, visibility === 'community' && styles.visToggleBtnActive]}
            onPress={() => setVisibility('community')}
            disabled={!communityName}
          >
            <Text style={[styles.visToggleText, visibility === 'community' && styles.visToggleTextActive]}>
              🏘️ Community
            </Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={[styles.postBtn, (!body.trim() || posting) && styles.postBtnDisabled]}
          onPress={submit}
          disabled={!body.trim() || posting}
        >
          {posting
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={styles.postBtnText}>Post</Text>}
        </TouchableOpacity>
      </View>
      {visibility === 'community' && communityName && (
        <Text style={styles.visHint}>Only visible to {communityName} members</Text>
      )}
      {visibility === 'public' && (
        <Text style={styles.visHint}>Visible to the whole city</Text>
      )}
    </View>
  );
}

function CommunityPicker({
  communities,
  currentId,
  loading,
  onPick,
  onCancel,
}: {
  communities: ApiCommunity[];
  currentId: string | null;
  loading: boolean;
  onPick: (id: string) => void;
  onCancel: () => void;
}) {
  return (
    <View style={styles.picker}>
      <Text style={styles.pickerTitle}>Switch community</Text>
      <Text style={styles.pickerSub}>Your posts will be attributed to the new community.</Text>
      {communities.map(c => (
        <TouchableOpacity
          key={c.id}
          style={[styles.pickerCard, c.id === currentId && styles.pickerCardActive]}
          onPress={() => c.id !== currentId && onPick(c.id)}
          disabled={loading || c.id === currentId}
        >
          <Text style={[styles.pickerCardName, c.id === currentId && styles.pickerCardNameActive]}>
            {c.name}
          </Text>
          <Text style={[styles.pickerCardCount, c.id === currentId && styles.pickerCardCountActive]}>
            {c.id === currentId ? 'current' : `${c.memberCount} members`}
          </Text>
        </TouchableOpacity>
      ))}
      {loading && <ActivityIndicator style={{ marginTop: 4 }} />}
      <TouchableOpacity onPress={onCancel} disabled={loading}>
        <Text style={styles.pickerCancel}>Cancel</Text>
      </TouchableOpacity>
    </View>
  );
}

type Tab = 'city' | 'community';

export default function HomeScreen() {
  const { user, logout, updateUser } = useSession();

  const [tab, setTab] = useState<Tab>('city');
  const [cityPosts, setCityPosts] = useState<ApiPost[]>([]);
  const [communityPosts, setCommunityPosts] = useState<ApiPost[]>([]);
  const [communities, setCommunities] = useState<ApiCommunity[]>([]);
  const [loadingCity, setLoadingCity] = useState(false);
  const [loadingCommunity, setLoadingCommunity] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [switchLoading, setSwitchLoading] = useState(false);

  const loadCity = useCallback(() => {
    setLoadingCity(true);
    fetchCityFeed()
      .then(setCityPosts)
      .catch(() => {})
      .finally(() => setLoadingCity(false));
  }, []);

  const loadCommunity = useCallback((communityId: string) => {
    setLoadingCommunity(true);
    fetchCommunityFeed(communityId)
      .then(setCommunityPosts)
      .catch(() => {})
      .finally(() => setLoadingCommunity(false));
  }, []);

  useEffect(() => {
    loadCity();
    fetchCommunities().then(setCommunities).catch(() => {});
  }, [loadCity]);

  useEffect(() => {
    if (user?.communityId) loadCommunity(user.communityId);
    else setCommunityPosts([]);
  }, [user?.communityId, loadCommunity]);

  const handlePost = async (body: string, visibility: 'public' | 'community') => {
    await createPost({ body, visibility });
    loadCity();
    if (user?.communityId) loadCommunity(user.communityId);
  };

  const handleSwitch = async (communityId: string) => {
    setSwitchLoading(true);
    try {
      const updated = await updateMe({ communityId });
      await updateUser(updated);
      setShowPicker(false);
    } catch {
      // leave picker open
    } finally {
      setSwitchLoading(false);
    }
  };

  const currentCommunity = communities.find(c => c.id === user?.communityId) ?? null;
  const otherCommunities = communities.filter(c => c.id !== user?.communityId);

  if (!user) return null;

  if (showPicker) {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <CommunityPicker
          communities={communities}
          currentId={user.communityId}
          loading={switchLoading}
          onPick={handleSwitch}
          onCancel={() => setShowPicker(false)}
        />
      </ScrollView>
    );
  }

  const activePosts = tab === 'city' ? cityPosts : communityPosts;
  const loading = tab === 'city' ? loadingCity : loadingCommunity;

  return (
    <ScrollView contentContainerStyle={styles.screen}>

      {/* Header */}
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>
            {currentCommunity?.name ?? 'No community'}
          </Text>
          <TouchableOpacity onPress={() => setShowPicker(true)}>
            <Text style={styles.switchLink}>switch community →</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity onPress={logout}>
          <Text style={styles.signOut}>Sign out</Text>
        </TouchableOpacity>
      </View>

      {/* Post composer */}
      <PostComposer communityName={currentCommunity?.name ?? null} onPost={handlePost} />

      {/* Tabs */}
      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, tab === 'city' && styles.tabActive]}
          onPress={() => setTab('city')}
        >
          <Text style={[styles.tabText, tab === 'city' && styles.tabTextActive]}>🌍 City</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, tab === 'community' && styles.tabActive]}
          onPress={() => setTab('community')}
        >
          <Text style={[styles.tabText, tab === 'community' && styles.tabTextActive]}>
            🏘️ {currentCommunity?.name ?? 'My Community'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Tab description */}
      <Text style={styles.tabDesc}>
        {tab === 'city'
          ? 'Public posts from all communities'
          : `All posts from ${currentCommunity?.name ?? 'your community'} — including community-only ones`}
      </Text>

      {/* Feed */}
      {loading ? (
        <ActivityIndicator style={{ marginTop: 24 }} />
      ) : activePosts.length === 0 ? (
        <Text style={styles.empty}>
          {tab === 'community' && !user.communityId
            ? 'Join a community to see its feed.'
            : 'No posts yet.'}
        </Text>
      ) : (
        <View style={styles.feed}>
          {activePosts.map(p => (
            <PostCard key={p.id} post={p} isSelf={p.author.id === user.id} />
          ))}
        </View>
      )}

      {/* Other communities callout (city tab only) */}
      {tab === 'city' && otherCommunities.length > 0 && (
        <View style={styles.lockedSection}>
          <Text style={styles.lockedTitle}>Community-only posts are hidden</Text>
          <Text style={styles.lockedBody}>
            Posts marked 🏘️ Community are only visible to members.
            Switch to your community tab to see them.
          </Text>
          <View style={styles.lockedList}>
            {otherCommunities.map(c => (
              <View key={c.id} style={styles.lockedPill}>
                <Text style={styles.lockedPillText}>🔒 {c.name}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { padding: 20, gap: 18, paddingBottom: 40 },

  header: { flexDirection: 'row', alignItems: 'flex-start' },
  headerTitle: { fontSize: 20, fontWeight: '700', letterSpacing: -0.3 },
  switchLink: { fontSize: 12, color: '#888', marginTop: 2 },
  signOut: { fontSize: 13, color: '#aaa', paddingTop: 4 },

  avatar: { backgroundColor: '#222', alignItems: 'center', justifyContent: 'center' },
  avatarHighlight: { backgroundColor: '#000' },
  avatarText: { color: '#fff', fontWeight: '700' },

  badge: { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, backgroundColor: '#f0f0f0' },
  badgeCommunity: { backgroundColor: '#e8f0fe' },
  badgeText: { fontSize: 11, color: '#666', fontWeight: '600' },
  badgeTextCommunity: { color: '#3367d6' },

  composer: { borderWidth: 1, borderColor: '#e0e0e0', borderRadius: 12, padding: 12, gap: 10 },
  composerInput: { fontSize: 15, color: '#000', minHeight: 60, textAlignVertical: 'top' },
  composerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  visibilityToggle: { flex: 1, flexDirection: 'row', borderRadius: 8, backgroundColor: '#f0f0f0', padding: 3 },
  visToggleBtn: { flex: 1, paddingVertical: 6, alignItems: 'center', borderRadius: 6 },
  visToggleBtnActive: { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 3, shadowOffset: { width: 0, height: 1 }, elevation: 1 },
  visToggleText: { fontSize: 12, color: '#888', fontWeight: '500' },
  visToggleTextActive: { color: '#000', fontWeight: '600' },
  postBtn: { backgroundColor: '#000', borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8, minWidth: 56, alignItems: 'center' },
  postBtnDisabled: { opacity: 0.4 },
  postBtnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  visHint: { fontSize: 11, color: '#aaa' },

  tabs: { flexDirection: 'row', borderRadius: 10, backgroundColor: '#f0f0f0', padding: 4 },
  tab: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  tabActive: { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, shadowOffset: { width: 0, height: 1 }, elevation: 2 },
  tabText: { fontSize: 13, fontWeight: '500', color: '#888' },
  tabTextActive: { color: '#000', fontWeight: '700' },
  tabDesc: { fontSize: 12, color: '#aaa', marginTop: -8 },

  feed: { gap: 12 },
  empty: { textAlign: 'center', color: '#bbb', fontSize: 14, marginTop: 16 },

  postCard: { borderWidth: 1, borderColor: '#eee', borderRadius: 12, padding: 14, gap: 10 },
  postCardSelf: { borderColor: '#ddd', backgroundColor: '#fafafa' },
  postTop: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  postMeta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  postName: { fontSize: 14, fontWeight: '600', color: '#000', flex: 1 },
  selfTag: { fontWeight: '400', color: '#aaa' },
  postSub: { fontSize: 12, color: '#aaa', marginTop: 2 },
  postBody: { fontSize: 15, color: '#222', lineHeight: 22 },

  lockedSection: { borderWidth: 1, borderColor: '#f0f0f0', borderRadius: 12, padding: 14, gap: 8, backgroundColor: '#fafafa' },
  lockedTitle: { fontSize: 13, fontWeight: '700', color: '#555' },
  lockedBody: { fontSize: 13, color: '#999', lineHeight: 18 },
  lockedList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  lockedPill: { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: '#ebebeb' },
  lockedPillText: { fontSize: 12, color: '#666' },

  picker: { gap: 14 },
  pickerTitle: { fontSize: 20, fontWeight: '700', letterSpacing: -0.3 },
  pickerSub: { fontSize: 14, color: '#666', marginTop: -6 },
  pickerCard: { borderWidth: 1, borderColor: '#ddd', borderRadius: 12, padding: 16, backgroundColor: '#fafafa' },
  pickerCardActive: { borderColor: '#000', backgroundColor: '#000' },
  pickerCardName: { fontSize: 16, fontWeight: '600', color: '#000' },
  pickerCardNameActive: { color: '#fff' },
  pickerCardCount: { fontSize: 13, color: '#888', marginTop: 2 },
  pickerCardCountActive: { color: '#ccc' },
  pickerCancel: { textAlign: 'center', fontSize: 14, color: '#555', paddingVertical: 4, marginTop: 4 },
});
