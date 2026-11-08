import {
  BODY_TIMEOUT_MS,
  HEADERS_TIMEOUT_MS,
  ApiError,
  api,
} from '../src/api/client';

const aborted = () =>
  Object.assign(new Error('aborted'), { name: 'AbortError' });

// A fetch that only ends when its signal aborts; with headersAt the headers arrive then, the body never.
function hang(headersAt?: number) {
  globalThis.fetch = jest.fn(
    (_url: string, init: RequestInit) =>
      new Promise((resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(aborted()));
        if (headersAt !== undefined) {
          setTimeout(
            () =>
              resolve({
                ok: true,
                status: 200,
                headers: new Headers(),
                text: () =>
                  new Promise((_r, rej) =>
                    init.signal?.addEventListener('abort', () =>
                      rej(aborted()),
                    ),
                  ),
              }),
            headersAt,
          );
        }
      }),
  ) as unknown as typeof fetch;
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('no headers within 10 s aborts the request', async () => {
  hang();
  const result = api('get', '/teams').catch(e => e);
  await jest.advanceTimersByTimeAsync(HEADERS_TIMEOUT_MS - 1);
  expect(await Promise.race([result, 'pending'])).toBe('pending');
  await jest.advanceTimersByTimeAsync(1);
  const e = await result;
  expect(e.name).toBe('AbortError');
  expect(e).not.toBeInstanceOf(ApiError);
});

test('a body that stalls for 20 s after the headers aborts', async () => {
  hang(HEADERS_TIMEOUT_MS - 1000);
  const result = api('get', '/teams').catch(e => e);
  await jest.advanceTimersByTimeAsync(
    HEADERS_TIMEOUT_MS - 1000 + BODY_TIMEOUT_MS - 1,
  );
  expect(await Promise.race([result, 'pending'])).toBe('pending');
  await jest.advanceTimersByTimeAsync(1);
  expect((await result).name).toBe('AbortError');
});

test('Retry-After is carried on the ApiError', async () => {
  globalThis.fetch = jest.fn(async () => ({
    ok: false,
    status: 429,
    headers: new Headers({ 'Retry-After': '30' }),
    text: async () => '{}',
  })) as unknown as typeof fetch;
  const e = await api('get', '/teams').catch(x => x);
  expect([e.status, e.retryAfterS]).toEqual([429, 30]);
});
