import * as Keychain from 'react-native-keychain';
import { api, ApiError } from '../src/api/client';
import {
  getAccessToken,
  getRefreshToken,
  saveTokens,
  setOnSessionEnded,
} from '../src/auth/session';

const pair = (n: number) => ({
  access_token: `access-${n}`,
  refresh_token: `refresh-${n}`,
  token_type: 'Bearer' as const,
  expires_in: 900,
});
const reply = (status: number, body?: unknown) => ({
  ok: status < 400,
  status,
  text: async () => (body === undefined ? '' : JSON.stringify(body)),
});

// Routes by URL and bearer token so the order of concurrent calls does not matter.
function server(refresh: () => ReturnType<typeof reply>) {
  const calls: string[] = [];
  globalThis.fetch = jest.fn(async (url: string, init: RequestInit) => {
    const auth = (init.headers as Record<string, string>).Authorization;
    calls.push(`${url.split('/v1')[1]} ${auth ?? ''}`.trim());
    if (url.endsWith('/auth/refresh')) {
      return refresh();
    }
    return auth === 'Bearer access-2' ? reply(200, []) : reply(401, {});
  }) as unknown as typeof fetch;
  return calls;
}

beforeEach(async () => {
  await Keychain.resetGenericPassword({ service: 'floorwars.auth' });
  await saveTokens(pair(1));
});

test('a 401 refreshes, stores the rotated pair and retries once', async () => {
  const calls = server(() => reply(200, pair(2)));
  await expect(api('get', '/teams')).resolves.toEqual([]);
  expect(calls).toEqual([
    '/teams Bearer access-1',
    '/auth/refresh',
    '/teams Bearer access-2',
  ]);
  expect(await getRefreshToken()).toBe('refresh-2');
});

test('concurrent 401s share one refresh call', async () => {
  const calls = server(() => reply(200, pair(2)));
  await Promise.all([api('get', '/teams'), api('get', '/teams')]);
  expect(calls.filter(c => c === '/auth/refresh')).toHaveLength(1);
});

test('a second 401 after the refresh is surfaced, not retried again', async () => {
  const calls = server(() => reply(200, pair(3)));
  await expect(api('get', '/teams')).rejects.toBeInstanceOf(ApiError);
  expect(calls.filter(c => c === '/auth/refresh')).toHaveLength(1);
  expect(calls.filter(c => c.startsWith('/teams'))).toHaveLength(2);
});

test('refresh-token reuse (401 on refresh) signs out and clears the Keychain', async () => {
  const ended = jest.fn();
  setOnSessionEnded(ended);
  server(() => reply(401, { title: 'Refresh token reused' }));
  await expect(api('get', '/teams')).rejects.toMatchObject({ status: 401 });
  expect(ended).toHaveBeenCalledTimes(1);
  expect(await getAccessToken()).toBeNull();
  expect(await getRefreshToken()).toBeNull();
  setOnSessionEnded(undefined);
});

test('a network failure during refresh keeps the session', async () => {
  server(() => {
    throw new TypeError('Network request failed');
  });
  await expect(api('get', '/teams')).rejects.toBeInstanceOf(TypeError);
  expect(await getRefreshToken()).toBe('refresh-1');
});

test('a wrong code on /auth/verify does not trigger a refresh', async () => {
  const calls = server(() => reply(200, pair(2)));
  await expect(
    api('post', '/auth/verify', {
      body: {
        email: 'a@b.ro',
        code: '123456',
        device: { id: 'x', model: 'm', has_barometer: true },
      },
    }),
  ).rejects.toMatchObject({ status: 401 });
  expect(calls.some(c => c === '/auth/refresh')).toBe(false);
});
