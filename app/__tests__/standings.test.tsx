import { act, render, screen } from '@testing-library/react-native';
import { withTiming } from 'react-native-reanimated';
import { api, ApiError } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { useGameEvents } from '../src/realtime/useGameEvents';
import {
  FLIP_ANIMATION_MS,
  BuildingScreen,
} from '../src/screens/BuildingScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
jest.mock('../src/realtime/useGameEvents', () => ({
  useGameEvents: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const hook = useGameEvents as jest.Mock;

const AC = { team_id: 1, code: 'AC', color_hex: '#112233', points: 30 };
const ETC = { team_id: 2, code: 'ETC', color_hex: '#445566', points: 10 };
const standings = (over = {}) => ({
  building_id: 7,
  season_id: 1,
  owner: { id: 1, code: 'AC', color_hex: '#112233' },
  claimed_at: '2026-11-10T10:00:00Z',
  teams: [ETC, AC], // unsorted on purpose
  ...over,
});
let standingsResult: () => Promise<unknown>;
let standingsCalls = 0;

beforeEach(() => {
  jest.clearAllMocks();
  clearReadCache();
  standingsCalls = 0;
  standingsResult = async () => standings();
  apiMock.mockImplementation(async (_m: string, path: string) => {
    if (path === '/buildings') {
      return [{ id: 7, name: 'Library' }];
    }
    standingsCalls++;
    return standingsResult();
  });
});

const show = (buildingId: number | string = 7) =>
  render(
    <BuildingScreen {...({ route: { params: { buildingId } } } as any)} />,
  );
const flip = (e: object) =>
  act(() => hook.mock.calls[hook.mock.calls.length - 1][0](e));

test('the drawing names the shares, list is most points first', async () => {
  await show();
  expect(await screen.findByText('Library')).toBeTruthy();
  expect(
    screen.getByLabelText(
      'Library. Owned by AC. AC 75 percent, ETC 25 percent.',
    ),
  ).toBeTruthy();
  const labels = screen
    .getAllByLabelText(/points$/)
    .map(n => n.props.accessibilityLabel);
  expect(labels).toEqual(['AC: 30 points', 'ETC: 10 points']);
});

test('owner heading, with and without an owner', async () => {
  await show();
  expect(await screen.findByText('Owned by AC')).toBeTruthy();
  await screen.unmount();
  clearReadCache();
  standingsResult = async () => standings({ owner: null, claimed_at: null });
  await show();
  expect(await screen.findByText('Nobody owns this building yet')).toBeTruthy();
});

test('a deep-link id arrives as a string', async () => {
  await show('7');
  await screen.findByText('Owned by AC');
  expect(apiMock).toHaveBeenCalledWith('get', '/buildings/{id}/standings', {
    path: { id: 7 },
  });
});

test('a flip for this building animates the owner colour, then refetches', async () => {
  jest.useFakeTimers();
  await show();
  await screen.findByText('Owned by AC');
  expect(standingsCalls).toBe(1);
  await flip({
    type: 'building_flipped',
    building_id: 7,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  expect(withTiming).toHaveBeenCalledWith('#445566', {
    duration: FLIP_ANIMATION_MS,
  });
  expect(standingsCalls).toBe(1);
  await act(async () => {
    jest.advanceTimersByTime(FLIP_ANIMATION_MS);
  });
  expect(standingsCalls).toBe(2);
  jest.useRealTimers();
});

test('a flip for another building does nothing', async () => {
  jest.useFakeTimers();
  await show();
  await screen.findByText('Owned by AC');
  await flip({
    type: 'building_flipped',
    building_id: 8,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  await flip({ type: 'season_state', paused: false, ends_at: 'x' });
  await act(async () => {
    jest.advanceTimersByTime(5 * FLIP_ANIMATION_MS);
  });
  expect(withTiming).not.toHaveBeenCalled();
  expect(standingsCalls).toBe(1);
  jest.useRealTimers();
});

test('empty, loading, offline, 404 and other error states', async () => {
  standingsResult = async () => standings({ teams: [], owner: null });
  await show();
  expect(
    await screen.findByText(
      'No team has points here in the last 7 days. Climb the stairs to claim it.',
    ),
  ).toBeTruthy();
  await screen.unmount();

  clearReadCache();
  standingsResult = () => new Promise(() => {});
  await show();
  expect(screen.getByLabelText('Loading')).toBeTruthy();
  await screen.unmount();

  const cases: [() => Promise<unknown>, string][] = [
    [
      () => Promise.reject(new TypeError('Network request failed')),
      "Can't reach the server. Check your connection, then pull down to retry.",
    ],
    [
      () => Promise.reject(new ApiError(404, {})),
      "This building doesn't exist anymore.",
    ],
    [
      () => Promise.reject(new ApiError(500, {})),
      'Something went wrong loading this. Pull down to retry.',
    ],
  ];
  for (const [result, text] of cases) {
    clearReadCache();
    standingsResult = result;
    await show();
    expect(await screen.findByText(text)).toBeTruthy();
    await screen.unmount();
  }
});

test('a failed refresh shows the cached copy with its label', async () => {
  jest.useFakeTimers();
  await show();
  await screen.findByText('Owned by AC');
  standingsResult = () =>
    Promise.reject(new TypeError('Network request failed'));
  await flip({
    type: 'building_flipped',
    building_id: 7,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  await act(async () => {
    jest.advanceTimersByTime(FLIP_ANIMATION_MS);
  });
  expect(screen.getByText('Owned by AC')).toBeTruthy();
  expect(
    screen.getByText(
      /^Last updated \d{1,2}[:.]\d{2}.*\. Can't reach the server\.$/,
    ),
  ).toBeTruthy();
  jest.useRealTimers();
});
