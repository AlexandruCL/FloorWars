import { api } from '../api/client';
import { getRefreshToken } from './session';

// Sign-out must not wait long on a slow network.
export const LOGOUT_TIMEOUT_MS = 5000;

// Best effort (contract 0.7.0): asks the server to revoke the refresh token family. Any error,
// including no token and a timeout, is swallowed so the caller can always clear the session.
export async function revokeRefreshToken(): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const refresh_token = await getRefreshToken();
    if (!refresh_token) {
      return;
    }
    await Promise.race([
      api('post', '/auth/logout', { body: { refresh_token } }),
      new Promise<void>(resolve => {
        timer = setTimeout(resolve, LOGOUT_TIMEOUT_MS);
      }),
    ]);
  } catch {
  } finally {
    clearTimeout(timer);
  }
}
