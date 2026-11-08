import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { Platform } from 'react-native';
import { FloorSensors } from '../src/native/floorSensors';
import { HomeScreen } from '../src/screens/HomeScreen';
import { minutesLeftMs, showBatteryHint } from '../src/screens/homeStatus';
import * as worker from '../src/sync/syncWorker';

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

async function show() {
  await render(<HomeScreen {...({ navigation } as any)} />);
}

beforeEach(() => {
  jest.clearAllMocks();
  worker.resetSyncForTests();
  jest.spyOn(Date, 'now').mockReturnValue(NOW);
  native.getStatus.mockResolvedValue(status());
  native.getActiveCheckin.mockResolvedValue(checkin());
  native.getPendingCount.mockResolvedValue(3);
  native.isIgnoringBatteryOptimizations.mockResolvedValue(true);
  Platform.OS = 'android';
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

test('loading first', async () => {
  native.getStatus.mockReturnValue(new Promise(() => {}));
  await render(<HomeScreen {...({ navigation } as any)} />);
  expect(screen.getByText('Loading status...')).toBeTruthy();
});

test('running with a check-in shows every value', async () => {
  await show();
  expect(screen.getByLabelText('Detection: Running')).toBeTruthy();
  expect(screen.getByLabelText('Check-in: Building, 89 min left')).toBeTruthy();
  expect(screen.getByLabelText('Waiting to upload: 3')).toBeTruthy();
  expect(
    screen.getByLabelText('Last upload: Not yet since the app opened'),
  ).toBeTruthy();
  expect(screen.queryByText(/Battery saving/)).toBeNull();
});

test('a known building name is shown', async () => {
  native.getActiveCheckin.mockResolvedValue(
    checkin({ building_name: 'Tower A' }),
  );
  await show();
  expect(screen.getByLabelText('Check-in: Tower A, 89 min left')).toBeTruthy();
});

test('no active check-in says what to do, and no segment yet is stated', async () => {
  native.getActiveCheckin.mockResolvedValue(null);
  native.getStatus.mockResolvedValue(status({ last_segment_ms: null }));
  await show();
  expect(screen.getByLabelText('Check-in: None')).toBeTruthy();
  expect(screen.getByText(/Check in at the building/)).toBeTruthy();
  expect(screen.getByLabelText('Last segment: No segment yet')).toBeTruthy();
});

test('service not running', async () => {
  native.getStatus.mockResolvedValue(status({ detecting: false }));
  await show();
  expect(screen.getByLabelText('Detection: Not running')).toBeTruthy();
  expect(screen.getByText(/Detection is not running/)).toBeTruthy();
});

test('unknown values are called unknown, not invented', async () => {
  native.getPendingCount.mockRejectedValue(new Error('x'));
  native.getActiveCheckin.mockRejectedValue(new Error('x'));
  await show();
  expect(screen.getByLabelText('Waiting to upload: Unknown')).toBeTruthy();
  expect(screen.getByLabelText('Check-in: Unknown')).toBeTruthy();
});

test('error state when nothing can be read', async () => {
  native.getStatus.mockRejectedValue(new Error('x'));
  native.getActiveCheckin.mockRejectedValue(new Error('x'));
  native.getPendingCount.mockRejectedValue(new Error('x'));
  await show();
  expect(screen.getByText(/Could not read the sensor service/)).toBeTruthy();
  expect(screen.getByText('Sync now')).toBeTruthy();
});

test.each([
  ['offline', /No connection to the server/],
  ['error', /did not finish/],
])('last sync %s is reported', async (outcome, text) => {
  jest.spyOn(worker, 'getSyncState').mockReturnValue({
    running: false,
    stuck: null,
    notBeforeMs: null,
    last: { at: NOW, outcome: outcome as any, synced: 0, rejected: 0 },
  });
  await show();
  expect(screen.getByText(text)).toBeTruthy();
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
  expect(screen.getByText(text)).toBeTruthy();
});

test('battery hint shows when not exempt and opens the setting', async () => {
  native.isIgnoringBatteryOptimizations.mockResolvedValue(false);
  await show();
  expect(screen.getByText(/Battery saving can stop/)).toBeTruthy();
  await fireEvent.press(screen.getByText('Open battery settings'));
  expect(native.openBatteryOptimizationSettings).toHaveBeenCalled();
});

test('no battery hint on iOS even when not exempt', async () => {
  Platform.OS = 'ios';
  native.isIgnoringBatteryOptimizations.mockResolvedValue(false);
  await show();
  expect(screen.queryByText(/Battery saving/)).toBeNull();
});

test('Sync now runs the worker and Check in navigates', async () => {
  const sync = jest
    .spyOn(worker, 'syncNow')
    .mockResolvedValue(worker.getSyncState());
  await show();
  await fireEvent.press(screen.getByText('Sync now'));
  await waitFor(() => expect(sync).toHaveBeenCalledTimes(1));
  await fireEvent.press(screen.getByText('Check in'));
  expect(navigation.navigate).toHaveBeenCalledWith('Checkin');
});
