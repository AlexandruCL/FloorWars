export type AuthStackParamList = {
  Email: undefined;
  Otp: { email: string };
  Team: undefined;
};

export type MainStackParamList = {
  Home: undefined;
  Checkin: undefined;
  SensorLogger: undefined;
  // A deep link delivers the id as a string.
  Standings: { buildingId: number | string };
  Leaderboards: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
};
