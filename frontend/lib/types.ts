export type ApiCommunity = {
  id: string;
  name: string;
  memberCount: number;
};

export type ApiPost = {
  id: string;
  body: string;
  visibility: 'public' | 'community';
  createdAt: string;
  communityId: string | null;
  communityName: string | null;
  author: ApiUser;
};

export type ApiUser = {
  id: string;
  username: string;
  displayName: string;
  communityId: string | null;
  avatar: string;
  allowFollowers: boolean;
  defaultPostVisibility: 'public' | 'community' | 'followers' | 'private';
  hideCommunityFromNonFriends: boolean;
  onboardingComplete: boolean;
  viewerRelationship: 'self' | 'friend' | 'follower' | 'stranger' | null;
};
