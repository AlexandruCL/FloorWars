import { ApiError } from '../src/api/client';
import { getDeviceId } from '../src/auth/session';
import { FloorSensors } from '../src/native/floorSensors';
import {
  BACKOFF_BASE_MS,
  BACKOFF_CAP_MS,
  BATCH_SIZE,
  MAX_ATTEMPTS,
  deps,
  getSyncState,
  idempotencyKey,
  resetSyncForTests,
  setFlipHandler,
  syncNow,
} from '../src/sync/syncWorker';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const { api } = jest.requireMock('../src/api/client') as { api: jest.Mock };
const native = FloorSensors as unknown as Record<string, jest.Mock>;

const TEN = [
  'id',
  'checkin_id',
  'started_at',
  'building_id',
  'ascent_m',
  'duration_s',
  'vert_speed_mps',
  'steps',
  'stair_prob',
  'classifier_version',
];
const seg = (n: number) => ({
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  checkin_id: 'c1',
  started_at: '2026-11-08T10:00:00Z',
  building_id: 1,
  ascent_m: 3,
  duration_s: 20,
  vert_speed_mps: 0.15,
  steps: 20,
  stair_prob: 0.9,
  classifier_version: 'v1',
});
const ok = (
  accepted: object[],
  rejected: object[] = [],
  flips: object[] = [],
) => ({
  accepted,
  rejected,
  flips,
});
const acc = (s: { id: string }) => ({ id: s.id, steps_scored: 20, points: 5 });
const echoAll = async (_m: string, _p: string, o: any) =>
  ok(o.body.segments.map(acc));

// A fake outbox: getPending returns the rows that have not been marked yet.
function outbox(rows: ReturnType<typeof seg>[]) {
  let left = [...rows];
  native.getPending.mockImplementation(async (n: number) => left.slice(0, n));
  const drop = async (ids: string[]) => {
    left = left.filter(r => !ids.includes(r.id));
  };
  native.markSynced.mockImplementation(drop);
  native.markRejected.mockImplementation(drop);
  return () => left.length;
}

const sleeps: number[] = [];
beforeEach(() => {
  jest.clearAllMocks();
  resetSyncForTests();
  sleeps.length = 0;
  deps.now = () => 1_000_000;
  deps.random = () => 0.5;
  deps.sleep = async ms => {
    sleeps.push(ms);
  };
  api.mockReset();
  jest.spyOn(console, 'warn').mockImplementation(() => {});
});

test('batches stay within the contract limit and carry device_id and the ten fields', async () => {
  expect(BATCH_SIZE).toBeLessThanOrEqual(100);
  const rows = Array.from({ length: BATCH_SIZE + 5 }, (_, i) => seg(i + 1));
  const left = outbox(rows);
  api.mockImplementation(echoAll);
  const state = await syncNow();
  expect(state.last).toMatchObject({
    outcome: 'synced',
    synced: BATCH_SIZE + 5,
  });
  expect(left()).toBe(0);
  expect(api).toHaveBeenCalledTimes(2);
  const [method, path, options] = api.mock.calls[0];
  expect([method, path]).toEqual(['post', '/segments']);
  expect(options.body.segments).toHaveLength(BATCH_SIZE);
  expect(options.body.device_id).toBe(await getDeviceId());
  expect(Object.keys(options.body)).toEqual(['device_id', 'segments']);
  expect(Object.keys(options.body.segments[0]).sort()).toEqual([...TEN].sort());
});

test('the idempotency key is reused on retry and new for a new batch', async () => {
  outbox([seg(1), seg(2)]);
  api.mockRejectedValueOnce(new TypeError('Network request failed'));
  api.mockImplementation(echoAll);
  await syncNow();
  const keys = api.mock.calls.map(c => c[2].header['Idempotency-Key']);
  expect(keys[0]).toBe(keys[1]);
  expect(keys[0]).toBe(idempotencyKey([seg(2).id, seg(1).id]));
  expect(idempotencyKey([seg(3).id])).not.toBe(keys[0]);
  expect(keys[0].length).toBeLessThan(255);
});

test('accepted, repeat without points, unknown reason and flips', async () => {
  const [a, b, c, d] = [seg(1), seg(2), seg(3), seg(4)];
  const left = outbox([a, b, c, d]);
  const flips = [{ building_id: 1, from_team: null, to_team: 'AC', at: 'x' }];
  const onFlips = jest.fn();
  setFlipHandler(onFlips);
  api.mockResolvedValue(
    ok(
      [acc(a), { id: b.id, steps_scored: 20 }], // a repeat: no points
      [
        { id: c.id, reason: 'overlap' }, // not in the 0.5.0 enum
        { id: d.id, reason: 'no_team' },
      ],
      flips,
    ),
  );
  const state = await syncNow();
  expect(native.markSynced).toHaveBeenCalledWith([a.id, b.id]);
  expect(native.markRejected).toHaveBeenCalledWith([c.id], 'overlap');
  expect(native.markRejected).toHaveBeenCalledWith([d.id], 'no_team');
  expect(onFlips).toHaveBeenCalledWith(flips);
  expect(state.last).toMatchObject({ synced: 2, rejected: 2 });
  expect(left()).toBe(0);
});

test('backoff uses full jitter with a fixed random source, then the batch stays pending', async () => {
  const left = outbox([seg(1)]);
  api.mockRejectedValue(new ApiError(500, {}));
  const state = await syncNow();
  expect(state.last?.outcome).toBe('offline');
  expect(api).toHaveBeenCalledTimes(MAX_ATTEMPTS);
  expect(sleeps).toEqual(
    Array.from(
      { length: MAX_ATTEMPTS - 1 },
      (_, i) => 0.5 * Math.min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * 2 ** i),
    ),
  );
  expect(left()).toBe(1);
  expect(native.markSynced).not.toHaveBeenCalled();
});

test.each([429, 503])(
  '%i with Retry-After waits, and triggers before that time are skipped',
  async status => {
    outbox([seg(1)]);
    api.mockRejectedValue(new ApiError(status, {}, 120));
    expect((await syncNow()).last?.outcome).toBe('waiting');
    expect(getSyncState().notBeforeMs).toBe(1_000_000 + 120_000);
    expect(sleeps).toEqual([]);
    await syncNow();
    expect(api).toHaveBeenCalledTimes(1);
    deps.now = () => 1_000_000 + 120_000;
    api.mockResolvedValue(ok([acc(seg(1))]));
    expect((await syncNow()).last?.outcome).toBe('synced');
  },
);

test('a 503 without Retry-After backs off and recovers', async () => {
  outbox([seg(1)]);
  api.mockRejectedValueOnce(new ApiError(503, {}));
  api.mockResolvedValue(ok([acc(seg(1))]));
  expect((await syncNow()).last?.outcome).toBe('synced');
  expect(sleeps).toEqual([0.5 * BACKOFF_BASE_MS]);
});

test('401 after the client refresh stops the worker', async () => {
  const left = outbox([seg(1)]);
  api.mockRejectedValue(new ApiError(401, {}));
  expect((await syncNow()).last?.outcome).toBe('signed_out');
  expect(api).toHaveBeenCalledTimes(1);
  expect(left()).toBe(1);
});

test.each([
  [422, 'https://api.floorwars.me/problems/validation', 'validation'],
  [403, 'https://api.floorwars.me/problems/device-unknown', 'device-unknown'],
])(
  '%i stops, marks nothing, logs once and keeps the rows pending',
  async (status, type, kind) => {
    const left = outbox([seg(1), seg(2)]);
    api.mockRejectedValue(
      new ApiError(status, { type, detail: 'secret detail' }),
    );
    const state = await syncNow();
    expect(state.last?.outcome).toBe('stuck');
    expect(state.stuck).toEqual({ kind, type });
    expect(api).toHaveBeenCalledTimes(1);
    expect(native.markSynced).not.toHaveBeenCalled();
    expect(native.markRejected).not.toHaveBeenCalled();
    expect(left()).toBe(2);
    await syncNow(); // stays stopped: no second request, no second log
    expect(api).toHaveBeenCalledTimes(1);
    expect(console.warn).toHaveBeenCalledTimes(1);
    expect(String((console.warn as jest.Mock).mock.calls[0][0])).not.toContain(
      'secret',
    );
  },
);

test('single flight: a second trigger gets the running sync', async () => {
  outbox([seg(1)]);
  let release!: () => void;
  const pendingCall = new Promise<unknown>(resolve => {
    release = () => resolve(ok([acc(seg(1))]));
  });
  api.mockImplementation(() => pendingCall);
  const first = syncNow();
  const second = syncNow();
  await new Promise<void>(r => setImmediate(r));
  release();
  expect(await second).toBe(await first);
  expect(api).toHaveBeenCalledTimes(1);
});

test('a timeout (AbortError) is retried like a network error', async () => {
  outbox([seg(1)]);
  api.mockRejectedValueOnce(
    Object.assign(new Error('aborted'), { name: 'AbortError' }),
  );
  api.mockResolvedValue(ok([acc(seg(1))]));
  expect((await syncNow()).last?.outcome).toBe('synced');
  expect(sleeps).toHaveLength(1);
});

test('a batch that partly fails: the synced row is not resent, the other is retried', async () => {
  const [a, b] = [seg(1), seg(2)];
  const left = outbox([a, b]);
  api.mockResolvedValue(ok([acc(a)], [{ id: b.id, reason: 'speed' }]));
  native.markRejected.mockRejectedValueOnce(new Error('db locked'));
  expect((await syncNow()).last?.outcome).toBe('error');
  expect(left()).toBe(1);
  api.mockResolvedValue(ok([], [{ id: b.id, reason: 'speed' }]));
  expect((await syncNow()).last).toMatchObject({
    outcome: 'synced',
    rejected: 1,
  });
  expect(api.mock.calls[1][2].body.segments.map((s: any) => s.id)).toEqual([
    b.id,
  ]);
  expect(left()).toBe(0);
});

test('an answer that covers no sent id ends the run instead of looping', async () => {
  outbox([seg(1)]);
  api.mockResolvedValue(ok([]));
  expect((await syncNow()).last?.outcome).toBe('error');
  expect(api).toHaveBeenCalledTimes(1);
});

test('nothing pending is idle and sends nothing', async () => {
  outbox([]);
  expect((await syncNow()).last?.outcome).toBe('idle');
  expect(api).not.toHaveBeenCalled();
});

test.each([
  ['uploaded', () => api.mockResolvedValue(ok([acc(seg(1))])), 'synced'],
  [
    'rejected',
    () => api.mockResolvedValue(ok([], [{ id: seg(1).id, reason: 'speed' }])),
    'synced',
  ],
  ['failed', () => api.mockRejectedValue(new ApiError(500, {})), 'offline'],
  ['no connection', () => api.mockRejectedValue(new TypeError('x')), 'offline'],
])('an idle run does not replace a %s result', async (_n, arrange, outcome) => {
  outbox([seg(1)]);
  arrange();
  const first = (await syncNow()).last;
  expect(first?.outcome).toBe(outcome);
  if (outcome === 'offline') {
    native.getPending.mockResolvedValue([]); // later the outbox is empty
  }
  deps.now = () => 2_000_000;
  const after = (await syncNow()).last;
  expect(after).toEqual(first);
});

test('a failure after an idle run still shows', async () => {
  outbox([]);
  expect((await syncNow()).last?.outcome).toBe('idle');
  outbox([seg(1)]);
  api.mockRejectedValue(new ApiError(500, {}));
  expect((await syncNow()).last?.outcome).toBe('offline');
});
