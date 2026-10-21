import * as Keychain from 'react-native-keychain';

// Stand-in for the OTP sign-in (POST /auth/otp, /auth/verify) until the real auth lands.
const SERVICE = 'floorwars.auth';
export const DUMMY_ACCESS_TOKEN = 'stub-access-token';

// Stores a dummy access token in the Android Keystore, then switches the navigator to Main.
export async function signInWithStub(onSignedIn: () => void): Promise<void> {
  await Keychain.setGenericPassword('stub', DUMMY_ACCESS_TOKEN, {
    service: SERVICE,
  });
  onSignedIn();
}

export async function getAccessToken(): Promise<string | null> {
  const credentials = await Keychain.getGenericPassword({ service: SERVICE });
  return credentials ? credentials.password : null;
}
