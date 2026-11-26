import type { NavigatorScreenParams } from '@react-navigation/native';

export type AuthStackParamList = {
  Email: undefined;
  Otp: { email: string };
  Team: undefined;
};

export type TabParamList = {
  Climb: undefined;
  Buildings: undefined;
  Ranks: undefined;
  You: undefined;
};

export type MainStackParamList = {
  Tabs: NavigatorScreenParams<TabParamList> | undefined;
  Checkin: undefined;
  SensorLogger: undefined;
  Building: { buildingId: number };
  History: undefined;
  LandingScan: undefined;
  Onboarding: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  Main: NavigatorScreenParams<MainStackParamList> | undefined;
};
