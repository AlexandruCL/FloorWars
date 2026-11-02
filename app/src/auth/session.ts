import * as Keychain from 'react-native-keychain';
import type { components } from '../api/schema';

type TokenPair = components['schemas']['TokenPair'];

// Tokens live in the Android Keystore through react-native-keychain, one JSON entry.
const TOKENS = 'floorwars.auth';
const DEVICE = 'floorwars.device';
const TEAM = 'floorwars.team';

type Stored = { access: string; refresh: string };

async function readTokens(): Promise<Stored | null> {
  const credentials = await Keychain.getGenericPassword({ service: TOKENS });
  return credentials ? (JSON.parse(credentials.password) as Stored) : null;
}

export async function getAccessToken(): Promise<string | null> {
  return (await readTokens())?.access ?? null;
}

export async function getRefreshToken(): Promise<string | null> {
  return (await readTokens())?.refresh ?? null;
}

export async function hasSession(): Promise<boolean> {
  return (await readTokens()) !== null;
}

// Refresh tokens rotate: always store the whole new pair.
export async function saveTokens(pair: TokenPair): Promise<void> {
  const value: Stored = {
    access: pair.access_token,
    refresh: pair.refresh_token,
  };
  await Keychain.setGenericPassword('tokens', JSON.stringify(value), {
    service: TOKENS,
  });
}

export async function hasChosenTeam(): Promise<boolean> {
  return (await Keychain.getGenericPassword({ service: TEAM })) !== false;
}

export async function markTeamChosen(): Promise<void> {
  await Keychain.setGenericPassword('team', '1', { service: TEAM });
}

// Random v4 id kept for the install; it is an identifier, not a secret, so Math.random is enough.
export async function getDeviceId(): Promise<string> {
  const stored = await Keychain.getGenericPassword({ service: DEVICE });
  if (stored) {
    return stored.password;
  }
  const id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.floor(Math.random() * 16);
    return (c === 'x' ? r : 8 + (r % 4)).toString(16);
  });
  await Keychain.setGenericPassword('device', id, { service: DEVICE });
  return id;
}

let onSessionEnded: (() => void) | undefined;

// The app root registers here so a failed refresh sends the user back to sign-in.
export function setOnSessionEnded(fn: (() => void) | undefined): void {
  onSessionEnded = fn;
}

// Clears the stored tokens and team flag (the device id stays) and tells the app.
export async function endSession(): Promise<void> {
  await Keychain.resetGenericPassword({ service: TOKENS });
  await Keychain.resetGenericPassword({ service: TEAM });
  onSessionEnded?.();
}
