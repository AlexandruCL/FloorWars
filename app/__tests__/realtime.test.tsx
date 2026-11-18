import { act, renderHook } from '@testing-library/react-native';
import { AppState } from 'react-native';
import type { AppStateStatus } from 'react-native';
import * as Keychain from 'react-native-keychain';
import { ApiError } from '../src/api/client';
import { endSession, saveTokens } from '../src/auth/session';
import { FloorSensors } from '../src/native/floorSensors';
import {
  loadRealtimeContext,
  MAX_EVENT_PAGES,
  pollGameEvents,
  startRealtimeLink,
} from '../src/realtime/realtime';
import { useGameEvents } from '../src/realtime/useGameEvents';
import type { WsEvent } from '../src/realtime/useGameEvents';
import { getSyncState, resetSyncForTests } from '../src/sync/syncWorker';
import { backgroundSyncTask } from '../src/sync/triggers';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const { api } = jest.requireMock('../src/api/client') as { api: jest.Mock };
const native = FloorSensors as unknown as Record<string, jest.Mock>;

type Listener<T> = (payload: T) => void;
let gameListeners: Listener<{ json: string }>[] = [];
let stateListeners: Listener<{ state: string }>[] = [];
const removed = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  api.mockReset();
  resetSyncForTests();
  gameListeners = [];
  stateListeners = [];
  native.onGameEvent.mockImplementation(l => {
    gameListeners.push(l);
    return { remove: () => removed('game') };
  });
  native.onRealtimeState.mockImplementation(l => {
    stateListeners.push(l);
    return { remove: () => removed('state') };
  });
  native.getLastEventId.mockResolvedValue(0);
  native.getPending.mockResolvedValue([]);
});

const flip = {
  type: 'building_flipped',
  event_id: 9,
  building_id: 7,
  from_team: 'AC',
  to_team: 'ETC',
  at: '2026-11-17T10:00:00Z',
};

describe('useGameEvents', () => {
  test('parses each event and passes it on', async () => {
    const seen: WsEvent[] = [];
    await renderHook(() => useGameEvents(e => seen.push(e)));
    await act(() => {
      gameListeners.forEach(l => l({ json: JSON.stringify(flip) }));
      gameListeners.forEach(l => l({ json: 'not json' }));
    });
    expect(seen).toEqual([flip]);
  });

  test('reports the socket state', async () => {
    const { result } = await renderHook(() => useGameEvents(() => {}));
    expect(result.current.status).toBe('closed');
    await act(() => stateListeners.forEach(l => l({ state: 'open' })));
    expect(result.current.status).toBe('open');
    await act(() => stateListeners.forEach(l => l({ state: 'auth_needed' })));
    expect(result.current.status).toBe('auth_needed');
  });

  test('unsubscribes on unmount', async () => {
    const { unmount } = await renderHook(() => useGameEvents(() => {}));
    await unmount();
    expect(removed).toHaveBeenCalledWith('game');
    expect(removed).toHaveBeenCalledWith('state');
  });

  test('a screen mounted later starts from the last known state', async () => {
    jest.spyOn(AppState, 'addEventListener').mockReturnValue({
      remove: jest.fn(),
    } as never);
    const stop = startRealtimeLink();
    stateListeners.forEach(l => l({ state: 'open' }));
    const { result } = await renderHook(() => useGameEvents(() => {}));
    expect(result.current.status).toBe('open');
    stop();
  });
});

describe('startRealtimeLink', () => {
  test('holds the socket in the foreground, releases it in the background', async () => {
    await Keychain.resetGenericPassword({ service: 'floorwars.auth' });
    await saveTokens({
      access_token: 'access-1',
      refresh_token: 'r',
      token_type: 'Bearer',
      expires_in: 900,
    } as never);
    let onChange: Listener<AppStateStatus> = () => {};
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_, l) => {
      onChange = l;
      return { remove: jest.fn() } as never;
    });
    const stop = startRealtimeLink();
    onChange('background');
    expect(native.stopRealtime).toHaveBeenCalledTimes(1);
    onChange('active');
    expect(native.startRealtime).toHaveBeenCalled();
    await act(async () => {});
    expect(native.configureRealtime).toHaveBeenLastCalledWith(
      'wss://api.floorwars.me/v1/ws',
      'access-1',
    );
    stop();
    expect(native.stopRealtime).toHaveBeenCalledTimes(2);
  });
});

test('the realtime context maps the team id to its code and passes the names', async () => {
  api.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/me/season-stats':
        return { team_id: 2 };
      case '/teams':
        return [
          { id: 1, code: 'AC', color_hex: '#000000' },
          { id: 2, code: 'ETC', color_hex: '#ffffff' },
        ];
      case '/buildings':
        return [{ id: 7, name: 'Politehnica', extra: 'x' }];
    }
  });
  await loadRealtimeContext();
  expect(native.setRealtimeContext).toHaveBeenCalledWith(
    'ETC',
    '[{"id":7,"name":"Politehnica"}]',
  );
});

describe('pollGameEvents', () => {
  const page = (last: number, hasMore: boolean) => ({
    items: [{ ...flip, event_id: last }],
    last_event_id: last,
    has_more: hasMore,
  });

  test('pages from the last handled id until has_more is false', async () => {
    native.getLastEventId.mockResolvedValue(40);
    api
      .mockResolvedValueOnce(page(140, true))
      .mockResolvedValueOnce(page(150, false));
    await pollGameEvents();
    expect(api.mock.calls.map(c => c[2].query)).toEqual([
      { since: 40, limit: 100 },
      { since: 140, limit: 100 },
    ]);
    expect(native.deliverPolledEvents).toHaveBeenCalledTimes(2);
    expect(JSON.parse(native.deliverPolledEvents.mock.calls[1][0])).toEqual(
      page(150, false),
    );
  });

  test('stops after five pages', async () => {
    let last = 0;
    api.mockImplementation(async () => page((last += 100), true));
    await pollGameEvents();
    expect(MAX_EVENT_PAGES).toBe(5);
    expect(api).toHaveBeenCalledTimes(5);
    expect(native.deliverPolledEvents).toHaveBeenCalledTimes(5);
  });
});

describe('backgroundSyncTask', () => {
  test('polls after the segment sync', async () => {
    api.mockResolvedValue(page0());
    await backgroundSyncTask();
    expect(api).toHaveBeenCalledWith('get', '/me/events', {
      query: { since: 0, limit: 100 },
    });
    expect(native.configureRealtime).toHaveBeenCalled();
  });

  test('a poll failure leaves the sync result unchanged', async () => {
    const segment = { id: 's1' };
    native.getPending
      .mockResolvedValueOnce([segment])
      .mockResolvedValueOnce([]);
    api.mockImplementation(async (_m: string, path: string) => {
      if (path === '/segments') {
        return { accepted: [{ id: 's1' }], rejected: [], flips: [] };
      }
      throw new ApiError(503, undefined);
    });
    await expect(backgroundSyncTask()).resolves.toBeUndefined();
    // The poll runs after the segment sync.
    expect(api.mock.calls.map(c => c[1])).toEqual(['/segments', '/me/events']);
    expect(getSyncState().last).toMatchObject({
      outcome: 'synced',
      synced: 1,
      rejected: 0,
    });
    expect(getSyncState().stuck).toBeNull();
  });
});

function page0() {
  return { items: [], last_event_id: 0, has_more: false };
}

test('endSession clears the realtime state', async () => {
  await endSession();
  expect(native.clearRealtime).toHaveBeenCalledTimes(1);
});
