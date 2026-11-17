import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { Text } from 'react-native';
import { api, ApiError } from '../src/api/client';
import type { CheckinDeps } from '../src/checkin/deps';
import {
  cooldownMsLeft,
  hasBarometer,
  LANDING_SCAN_COOLDOWN_MS,
  resetCooldownsForTests,
  submitLandingScan,
  tokenOk,
} from '../src/landing/landingScan';
import NativeFloorSensors from '../src/native/NativeFloorSensors';
import { HomeScreen } from '../src/screens/HomeScreen';
import { LandingScanScreen } from '../src/screens/LandingScanScreen';
import * as worker from '../src/sync/syncWorker';

jest.mock('../src/config/devFlags', () => ({
  DEV_SKIP_SIGN_IN: false,
  DEV_FORCE_NO_BAROMETER: true,
}));
jest.mock('../src/api/client', () => {
  const actual = jest.requireActual('../src/api/client');
  return { ...actual, api: jest.fn() };
});
const apiMock = api as unknown as jest.Mock;
const native = jest.mocked(NativeFloorSensors) as unknown as Record<
  string,
  jest.Mock
>;
const g = globalThis as unknown as { __DEV__: boolean };
const NOW = Date.UTC(2026, 10, 17, 12, 0, 0);
const status = (has_barometer: boolean) =>
  ({
    logging: false,
    label: '',
    has_barometer,
    buffered: 0,
    detecting: true,
    last_segment_ms: 0,
    rejected_count: 0,
    no_checkin_count: 0,
    longest_gap_s: 0,
    gaps_over_threshold: 0,
  } as any);
const checkin = {
  checkin_id: 'c',
  building_id: 7,
  building_name: 'Library',
  valid_until_ms: NOW + 60 * 60000,
};
const problem = (s: number, retry?: number) =>
  new ApiError(s, { status: s }, retry);

beforeEach(() => {
  jest.clearAllMocks();
  resetCooldownsForTests();
  worker.resetSyncForTests();
  g.__DEV__ = true;
  jest.spyOn(Date, 'now').mockReturnValue(NOW);
  native.getActiveCheckin.mockResolvedValue(checkin);
  native.getStatus.mockResolvedValue(status(true));
  native.getPendingCount.mockResolvedValue(0);
  native.isIgnoringBatteryOptimizations.mockResolvedValue(true);
});
afterEach(() => {
  g.__DEV__ = true;
  jest.restoreAllMocks();
});

describe('hasBarometer', () => {
  test('the dev flag forces false in a dev build', () => {
    expect(hasBarometer(status(true))).toBe(false);
  });
  test('the dev flag has no effect outside __DEV__', () => {
    g.__DEV__ = false;
    expect(hasBarometer(status(true))).toBe(true);
    expect(hasBarometer(status(false))).toBe(false);
    expect(hasBarometer(null)).toBe(true);
  });
});

describe('Home', () => {
  const navigation = {
    navigate: jest.fn(),
    addListener: jest.fn(() => () => {}),
  };
  const home = () => render(<HomeScreen {...({ navigation } as any)} />);
  test('scan entry only without a barometer, and it replaces the detection rows', async () => {
    g.__DEV__ = false;
    native.getStatus.mockResolvedValue(status(false));
    await home();
    await fireEvent.press(await screen.findByText('Scan at the stairs'));
    expect(navigation.navigate).toHaveBeenCalledWith('LandingScan');
    expect(screen.queryByText('Detection')).toBeNull();
  });
  test('with a barometer: detection rows, no scan entry', async () => {
    g.__DEV__ = false;
    await home();
    await screen.findByText('Detection');
    expect(screen.queryByText('Scan at the stairs')).toBeNull();
  });
});

describe('tokenOk', () => {
  test('length and control characters', () => {
    expect(tokenOk('a'.repeat(512))).toBe(true);
    expect(tokenOk('a'.repeat(513))).toBe(false);
    expect(tokenOk('')).toBe(false);
    expect(tokenOk('ab\ncd')).toBe(false);
    expect(tokenOk('ab\u0000cd')).toBe(false);
    expect(tokenOk('ab\u007fcd')).toBe(false);
    expect(tokenOk('anything-else.is/fine=')).toBe(true);
  });
});

describe('submitLandingScan', () => {
  test('sends exactly qr_token, building_id, scanned_at, unchanged', async () => {
    apiMock.mockResolvedValue({ id: 'x', building_id: 7 });
    const r = await submitLandingScan(7, ' tok ', NOW);
    expect(apiMock).toHaveBeenCalledWith('post', '/landing-scans', {
      body: {
        qr_token: ' tok ',
        building_id: 7,
        scanned_at: new Date(NOW).toISOString(),
      },
    });
    expect(r.text).toBe('Scan counted.');
  });
  test('points are shown as the server sent them', async () => {
    apiMock.mockResolvedValue({ id: 'x', building_id: 7, points: 5 });
    expect((await submitLandingScan(7, 't', NOW)).text).toBe(
      'Scan counted: +5 points.',
    );
  });
  test('flips go to the same handler as POST /segments', async () => {
    const handler = jest.fn();
    worker.setFlipHandler(handler);
    const flips = [{ building_id: 7, from_team: null, to_team: 'AC', at: 'x' }];
    apiMock.mockResolvedValue({ id: 'x', building_id: 7, flips });
    await submitLandingScan(7, 't', NOW);
    expect(handler).toHaveBeenCalledWith(flips);
  });
  test('a bad token sends nothing', async () => {
    const r = await submitLandingScan(7, 'a\nb', NOW);
    expect(r.text).toBe("This code isn't a FloorWars stair sticker.");
    expect(apiMock).not.toHaveBeenCalled();
  });
  test('cooldown after a 201, per building, then it ends', async () => {
    apiMock.mockResolvedValue({ id: 'x', building_id: 7 });
    await submitLandingScan(7, 't', NOW);
    apiMock.mockClear();
    expect(await submitLandingScan(7, 't', NOW + 1000)).toEqual({
      kind: 'cooldown',
      text: 'You can scan again in this building in 10 min.',
    });
    expect((await submitLandingScan(7, 't', NOW + 480_000)).text).toBe(
      'You can scan again in this building in 2 min.',
    );
    expect(apiMock).not.toHaveBeenCalled();
    await submitLandingScan(8, 't', NOW + 1000);
    expect(apiMock).toHaveBeenCalledTimes(1);
    await submitLandingScan(7, 't', NOW + LANDING_SCAN_COOLDOWN_MS);
    expect(apiMock).toHaveBeenCalledTimes(2);
  });
  test('a failed scan sets no cooldown', async () => {
    apiMock.mockRejectedValue(problem(403));
    await submitLandingScan(7, 't', NOW);
    expect(cooldownMsLeft(7, NOW)).toBe(0);
  });
  test('429 honours Retry-After; without it, the full cooldown', async () => {
    apiMock.mockRejectedValue(problem(429, 120));
    expect((await submitLandingScan(7, 't', NOW)).text).toBe(
      'Too many scans. Try again in 2 min.',
    );
    expect(cooldownMsLeft(7, NOW)).toBe(120_000);
    apiMock.mockRejectedValue(problem(429));
    await submitLandingScan(8, 't', NOW);
    expect(cooldownMsLeft(8, NOW)).toBe(LANDING_SCAN_COOLDOWN_MS);
  });
  test.each([
    [403, "This sticker isn't for this building, or it has expired."],
    [422, "This code isn't a FloorWars stair sticker."],
  ])('status %i', async (s, text) => {
    apiMock.mockRejectedValue(problem(s));
    expect((await submitLandingScan(7, 't', NOW)).text).toBe(text);
  });
  test('offline', async () => {
    apiMock.mockRejectedValue(new TypeError('Network request failed'));
    expect((await submitLandingScan(7, 't', NOW)).text).toBe(
      "Couldn't send the scan. Check your connection and try again.",
    );
  });
});

describe('LandingScanScreen', () => {
  let emit: (raw: string) => void;
  const deps: CheckinDeps = {
    ScannerView: ({ onScan }) => {
      emit = onScan;
      return <Text>camera</Text>;
    },
    requestCameraPermission: jest.fn(async () => true),
    getPosition: jest.fn(),
  };
  const navigation = { replace: jest.fn() };
  const open = () =>
    render(<LandingScanScreen {...({ navigation, deps } as any)} />);

  test('while reading the check-in: a spinner and no text', async () => {
    native.getActiveCheckin.mockReturnValue(new Promise(() => {}));
    await open();
    screen.getByLabelText('Loading');
    expect(screen.queryByText('Loading...')).toBeNull();
  });
  test('no check-in: message, no scan button', async () => {
    native.getActiveCheckin.mockResolvedValue(null);
    await open();
    await screen.findByText(
      'Check in at the building first, then scan the sticker on a stair landing.',
    );
    expect(screen.queryByText('Scan sticker')).toBeNull();
  });
  test('an expired check-in counts as none', async () => {
    native.getActiveCheckin.mockResolvedValue({
      ...checkin,
      valid_until_ms: NOW - 1,
    });
    await open();
    await screen.findByText(/Check in at the building first/);
  });
  test('scan sends the check-in building and shows the result', async () => {
    apiMock.mockResolvedValue({ id: 'x', building_id: 7, points: 3 });
    await open();
    await screen.findByText('Scan at the stairs of Library');
    screen.getByText(
      "Your phone has no barometer, so it can't measure climbs. Scan the sticker on a stair landing instead.",
    );
    await fireEvent.press(screen.getByText('Scan sticker'));
    await screen.findByText('camera');
    await act(async () => {
      emit('sticker-1');
    });
    await screen.findByText('Scan counted: +3 points.');
    expect(apiMock.mock.calls[0][2].body.building_id).toBe(7);
    expect(screen.queryByText('Scan sticker')).toBeNull();
    expect(cooldownMsLeft(7, NOW)).toBe(LANDING_SCAN_COOLDOWN_MS);
  });
  test('cooldown in force on open: message, no button', async () => {
    apiMock.mockResolvedValue({ id: 'x', building_id: 7 });
    await submitLandingScan(7, 't', NOW);
    await open();
    await screen.findByText('You can scan again in this building in 10 min.');
    expect(screen.queryByText('Scan sticker')).toBeNull();
  });
  test('camera denied points to Settings', async () => {
    (deps.requestCameraPermission as jest.Mock).mockResolvedValueOnce(false);
    await open();
    await fireEvent.press(await screen.findByText('Scan sticker'));
    await screen.findByText('Open Settings');
  });
  test('a failed scan can be retried', async () => {
    apiMock.mockRejectedValueOnce(problem(403));
    await open();
    await fireEvent.press(await screen.findByText('Scan sticker'));
    await screen.findByText('camera');
    await act(async () => {
      emit('x');
    });
    await screen.findByText(
      "This sticker isn't for this building, or it has expired.",
    );
    await waitFor(() => screen.getByText('Scan sticker'));
  });
});
