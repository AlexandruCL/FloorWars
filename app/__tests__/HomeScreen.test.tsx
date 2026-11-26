import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { Platform } from 'react-native';
import { api } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { FloorSensors } from '../src/native/floorSensors';
import { HomeScreen } from '../src/screens/HomeScreen';
import { minutesLeftMs, showBatteryHint } from '../src/screens/homeStatus';
import * as worker from '../src/sync/syncWorker';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const native = FloorSensors as unknown as Record<string, jest.Mock>;
const NOW = Date.UTC(2026, 10, 8, 12, 0, 0);
const navigation = {
  navigate: jest.fn(),
  addListener: jest.fn(() => () => {}),
};
const status = (over = {}) => ({
  logging: false,
  label: '',
  has_barometer: true,
  buffered: 0,
  detecting: true,
  last_segment_ms: NOW - 5 * 60000,
  rejected_count: 0,
  no_checkin_count: 0,
  longest_gap_s: 0,
  gaps_over_threshold: 0,
  ...over,
});
const checkin = (over = {}) => ({
  checkin_id: 'c',
  building_id: 1,
  building_name: null,
  valid_until_ms: NOW + 89 * 60000 - 1000,
  ...over,
});

const AC = { team_id: 1, code: 'AC', color_hex: '#1E88E5', points: 412 };
const ETC = { team_id: 2, code: 'ETC', color_hex: '#E53935', points: 280 };
let standings: () => Promise<unknown>;
let segments: () => Promise<unknown>;

async function show() {
  await render(<HomeScreen {...({ navigation } as any)} />);
}

beforeEach(() => {
  jest.clearAllMocks();
  clearReadCache();
  worker.resetSyncForTests();
  jest.spyOn(Date, 'now').mockReturnValue(NOW);
  native.getStatus.mockResolvedValue(status());
  native.getActiveCheckin.mockResolvedValue(checkin());
  native.getPendingCount.mockResolvedValue(0);
  native.isIgnoringBatteryOptimizations.mockResolvedValue(true);
  Platform.OS = 'android';
  standings = async () => ({
    building_id: 1,
    season_id: 3,
    owner: { id: 1, code: 'AC', color_hex: '#1E88E5' },
    claimed_at: null,
    teams: [ETC, AC],
  });
  segments = async () => ({ items: [], next_cursor: null });
  apiMock.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/seasons/active':
        return { id: 3, starts_at: '', ends_at: '2026-11-16T00:00:00Z' };
      case '/me/season-stats':
        return { season_id: 3, team_id: 2 };
      case '/teams':
        return [
          { id: 1, code: 'AC', color_hex: '#1E88E5' },
          { id: 2, code: 'ETC', color_hex: '#E53935' },
        ];
      case '/buildings':
        return [{ id: 1, name: 'Faculty of Automation and Computers' }];
      case '/buildings/{id}/standings':
        return standings();
      case '/me/segments':
        return segments();
    }
    throw new Error(`unexpected ${path}`);
  });
});
afterEach(() => jest.restoreAllMocks());

test('minutes left round up and never go below zero', () => {
  expect(minutesLeftMs(checkin(), NOW)).toBe(89);
  expect(minutesLeftMs(checkin({ valid_until_ms: NOW + 1 }), NOW)).toBe(1);
  expect(minutesLeftMs(checkin({ valid_until_ms: NOW - 5000 }), NOW)).toBe(0);
});

test('battery hint rule: Android and not exempt only', () => {
  expect(showBatteryHint('android', false)).toBe(true);
  expect(showBatteryHint('android', true)).toBe(false);
  expect(showBatteryHint('android', null)).toBe(false);
  expect(showBatteryHint('ios', false)).toBe(false);
});

test('checked in: your team, the building, the fight and the top teams', async () => {
  await show();
  expect((await screen.findAllByText('ETC')).length).toBeGreaterThan(0);
  expect(screen.getByText(/^Season 3, ends /)).toBeTruthy();
  expect(
    await screen.findByText('Faculty of Automation and Computers'),
  ).toBeTruthy();
  expect(
    await screen.findByText('AC owns it. ETC needs 133 points to take it.'),
  ).toBeTruthy();
  expect(screen.getByLabelText('AC: 412 points, 60 percent')).toBeTruthy();
  expect(screen.getByLabelText('ETC: 280 points, 40 percent')).toBeTruthy();
  expect(screen.getByText('89 min left')).toBeTruthy();
  await fireEvent.press(screen.getByText('All standings'));
  expect(navigation.navigate).toHaveBeenCalledWith('Building', {
    buildingId: 1,
  });
  await fireEvent.press(screen.getByText('Switch building'));
  expect(navigation.navigate).toHaveBeenCalledWith('Buildings');
});

test('the building name falls back to the check-in, then to its number', async () => {
  apiMock.mockImplementation(async (_m: string, path: string) => {
    throw new TypeError(`offline ${path}`);
  });
  native.getActiveCheckin.mockResolvedValue(
    checkin({ building_name: 'Tower A' }),
  );
  await show();
  expect(await screen.findByText('Tower A')).toBeTruthy();
  expect(await screen.findByText(/Standings can't be loaded/)).toBeTruthy();
});

test('not checked in: pick a building, or scan the entrance code', async () => {
  native.getActiveCheckin.mockResolvedValue(null);
  await show();
  expect(await screen.findByText('Pick a building to climb for')).toBeTruthy();
  expect(screen.getByText(/for 90 minutes/)).toBeTruthy();
  await fireEvent.press(screen.getByText('Pick a building'));
  expect(navigation.navigate).toHaveBeenCalledWith('Buildings');
  await fireEvent.press(screen.getByText('Scan entrance code'));
  expect(navigation.navigate).toHaveBeenCalledWith('Checkin');
});

test('an expired check-in counts as none', async () => {
  native.getActiveCheckin.mockResolvedValue(
    checkin({ valid_until_ms: NOW - 1 }),
  );
  await show();
  expect(await screen.findByText('Pick a building to climb for')).toBeTruthy();
});

test('today: floors (estimate) as the hero number, and it opens history', async () => {
  segments = async () => ({
    items: [
      {
        started_at: new Date(NOW - 60000).toISOString(),
        status: 'verified',
        steps_scored: 236,
        ascent_m: 35.4,
      },
    ],
    next_cursor: null,
  });
  await show();
  expect(await screen.findByText('11')).toBeTruthy();
  expect(screen.getByText('floors (estimate) today')).toBeTruthy();
  expect(screen.getByText('236 verified steps, 35.4 m up')).toBeTruthy();
  await fireEvent.press(screen.getByText('11'));
  expect(navigation.navigate).toHaveBeenCalledWith('History');
});

test('healthy: one line of status and no notices', async () => {
  await show();
  expect(await screen.findByText('Detection on.')).toBeTruthy();
  expect(screen.queryByText(/Battery saver/)).toBeNull();
});

test('climbs waiting with no problem: upload now', async () => {
  native.getPendingCount.mockResolvedValue(3);
  const sync = jest
    .spyOn(worker, 'syncNow')
    .mockResolvedValue(worker.getSyncState());
  await show();
  await fireEvent.press(await screen.findByText('Upload now'));
  await waitFor(() => expect(sync).toHaveBeenCalled());
  expect(screen.getByText('3 climbs waiting to upload.')).toBeTruthy();
});

test('detection off while checked in is a notice', async () => {
  native.getStatus.mockResolvedValue(status({ detecting: false }));
  await show();
  expect(
    await screen.findByText('Detection is off, so climbs are not recorded.'),
  ).toBeTruthy();
});

test('detection off without a check-in is normal, not a notice', async () => {
  native.getStatus.mockResolvedValue(status({ detecting: false }));
  native.getActiveCheckin.mockResolvedValue(null);
  await show();
  await screen.findByText('Pick a building to climb for');
  expect(screen.queryByText(/Detection is off/)).toBeNull();
});

test('error state when nothing can be read', async () => {
  native.getStatus.mockRejectedValue(new Error('x'));
  native.getActiveCheckin.mockRejectedValue(new Error('x'));
  native.getPendingCount.mockRejectedValue(new Error('x'));
  await show();
  expect(
    await screen.findByText(
      "Couldn't read the sensor service. Close and reopen the app.",
    ),
  ).toBeTruthy();
  expect(screen.getByText('Try again')).toBeTruthy();
});

test.each([
  ['offline', /No connection to the server/],
  ['error', /did not finish/],
])('last upload %s is a notice with Upload now', async (outcome, text) => {
  jest.spyOn(worker, 'getSyncState').mockReturnValue({
    running: false,
    stuck: null,
    notBeforeMs: null,
    last: { at: NOW, outcome: outcome as any, synced: 0, rejected: 0 },
  });
  await show();
  expect(await screen.findByText(text)).toBeTruthy();
  expect(screen.getByText('Upload now')).toBeTruthy();
});

test.each([
  ['validation', /server refused an upload/],
  ['device-unknown', /not registered to your account/],
])('a batch stuck on %s is reported', async (kind, text) => {
  jest.spyOn(worker, 'getSyncState').mockReturnValue({
    running: false,
    notBeforeMs: null,
    last: { at: NOW, outcome: 'stuck', synced: 0, rejected: 0 },
    stuck: { kind: kind as any, type: 't' },
  });
  await show();
  expect(await screen.findByText(text)).toBeTruthy();
});

test('battery notice when not exempt opens the setting', async () => {
  native.isIgnoringBatteryOptimizations.mockResolvedValue(false);
  await show();
  expect(await screen.findByText(/Battery saver can stop/)).toBeTruthy();
  await fireEvent.press(screen.getByText('Open battery settings'));
  expect(native.openBatteryOptimizationSettings).toHaveBeenCalled();
});

test('no battery notice on iOS even when not exempt', async () => {
  Platform.OS = 'ios';
  native.isIgnoringBatteryOptimizations.mockResolvedValue(false);
  await show();
  await screen.findByText('Detection on.');
  expect(screen.queryByText(/Battery saver/)).toBeNull();
});

test('at most two notices', async () => {
  native.getStatus.mockResolvedValue(status({ detecting: false }));
  native.isIgnoringBatteryOptimizations.mockResolvedValue(false);
  jest.spyOn(worker, 'getSyncState').mockReturnValue({
    running: false,
    stuck: null,
    notBeforeMs: null,
    last: { at: NOW, outcome: 'offline', synced: 0, rejected: 0 },
  });
  await show();
  await screen.findByText(/Detection is off/);
  expect(screen.getByText(/Battery saver/)).toBeTruthy();
  expect(screen.queryByText(/No connection to the server/)).toBeNull();
});
