export type AuthStackParamList = {
  Email: undefined;
  Otp: { email: string };
  Team: undefined;
};

export type MainStackParamList = {
  Home: undefined;
  SensorLogger: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
};
