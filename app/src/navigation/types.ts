import type { NavigatorScreenParams } from '@react-navigation/native';

export type AuthStackParamList = {
  Email: undefined;
  Otp: { email: string };
  Team: undefined;
};

export type MainStackParamList = {
  Home: undefined;
  Checkin: undefined;
  SensorLogger: undefined;
  Standings: { buildingId: number };
};

export type RootStackParamList = {
  Auth: undefined;
  Main: NavigatorScreenParams<MainStackParamList> | undefined;
};
