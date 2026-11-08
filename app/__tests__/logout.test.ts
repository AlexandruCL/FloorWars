import { api } from '../src/api/client';
import { LOGOUT_TIMEOUT_MS, revokeRefreshToken } from '../src/auth/logout';
import { saveTokens } from '../src/auth/session';
import * as Keychain from 'react-native-keychain';

jest.mock('../src/api/client', () => ({ api: jest.fn() }));

const apiMock = api as jest.Mock;
const pair = {
  access_token: 'a',
  refresh_token: 'r1',
  token_type: 'Bearer',
  expires_in: 900,
} as never;

beforeEach(async () => {
  apiMock.mockReset();
  await Keychain.resetGenericPassword({ service: 'floorwars.auth' });
});

test('posts the stored refresh token to /auth/logout', async () => {
  await saveTokens(pair);
  apiMock.mockResolvedValue(undefined);
  await revokeRefreshToken();
  expect(apiMock).toHaveBeenCalledTimes(1);
  expect(apiMock).toHaveBeenCalledWith('post', '/auth/logout', {
    body: { refresh_token: 'r1' },
  });
});

test('does nothing without a session', async () => {
  await revokeRefreshToken();
  expect(apiMock).not.toHaveBeenCalled();
});

test('swallows any error', async () => {
  await saveTokens(pair);
  apiMock.mockRejectedValue(new Error('network'));
  await expect(revokeRefreshToken()).resolves.toBeUndefined();
});

test('gives up after the timeout when the server does not answer', async () => {
  jest.useFakeTimers();
  try {
    await saveTokens(pair);
    apiMock.mockReturnValue(new Promise(() => {}));
    const done = jest.fn();
    const run = revokeRefreshToken().then(done);
    await jest.advanceTimersByTimeAsync(LOGOUT_TIMEOUT_MS - 1);
    expect(done).not.toHaveBeenCalled();
    await jest.advanceTimersByTimeAsync(1);
    await run;
    expect(done).toHaveBeenCalled();
  } finally {
    jest.useRealTimers();
  }
});
