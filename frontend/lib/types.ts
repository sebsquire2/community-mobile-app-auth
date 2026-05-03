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
