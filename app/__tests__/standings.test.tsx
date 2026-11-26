import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { api, ApiError } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { useGameEvents } from '../src/realtime/useGameEvents';
import { FloorSensors } from '../src/native/floorSensors';
import { BuildingScreen } from '../src/screens/BuildingScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
jest.mock('../src/realtime/useGameEvents', () => ({
  useGameEvents: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const hook = useGameEvents as jest.Mock;
const native = FloorSensors as unknown as Record<string, jest.Mock>;
const navigation = {
  navigate: jest.fn(),
  addListener: jest.fn(() => () => {}),
};

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
    if (path !== '/buildings/{id}/standings') {
      throw new TypeError('Network request failed');
    }
    standingsCalls++;
    return standingsResult();
  });
});

const show = (buildingId: number | string = 7) =>
  render(
    <BuildingScreen
      {...({ route: { params: { buildingId } }, navigation } as any)}
    />,
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
    .getAllByLabelText(/ points, /)
    .map(n => n.props.accessibilityLabel);
  expect(labels).toEqual([
    'AC: 30 points, 75 percent, holds it',
    'ETC: 10 points, 25 percent, needs 21 to take it',
  ]);
});

test('owner heading, with and without an owner', async () => {
  await show();
  expect(await screen.findByText(/^Owned by AC since /)).toBeTruthy();
  await screen.unmount();
  clearReadCache();
  standingsResult = async () => standings({ owner: null, claimed_at: null });
  await show();
  expect(await screen.findByText('Nobody owns it yet')).toBeTruthy();
});

test('a deep-link id arrives as a string', async () => {
  await show('7');
  await screen.findByText(/^Owned by AC since /);
  expect(apiMock).toHaveBeenCalledWith('get', '/buildings/{id}/standings', {
    path: { id: 7 },
  });
});

test('a flip for this building refetches the standings', async () => {
  await show();
  await screen.findByText(/^Owned by AC since /);
  expect(standingsCalls).toBe(1);
  await flip({
    type: 'building_flipped',
    building_id: 7,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  await act(async () => {});
  expect(standingsCalls).toBe(2);
});

test('a flip for another building does nothing', async () => {
  await show();
  await screen.findByText(/^Owned by AC since /);
  await flip({
    type: 'building_flipped',
    building_id: 8,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  await flip({ type: 'season_state', paused: false, ends_at: 'x' });
  await act(async () => {});
  expect(standingsCalls).toBe(1);
});

test('your team is marked and the sticky bar checks in', async () => {
  apiMock.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/buildings':
        return [{ id: 7, name: 'Library' }];
      case '/seasons/active':
        return { id: 1, starts_at: '', ends_at: '' };
      case '/me/season-stats':
        return { season_id: 1, team_id: 2 };
      case '/teams':
        return [
          { id: 1, code: 'AC', color_hex: '#112233' },
          { id: 2, code: 'ETC', color_hex: '#445566' },
        ];
    }
    return standingsResult();
  });
  await show();
  expect(await screen.findByText('Your team')).toBeTruthy();
  expect(
    screen.getByText('AC owns it. ETC needs 21 points to take it.'),
  ).toBeTruthy();
  await fireEvent.press(screen.getByText('Check in here'));
  expect(navigation.navigate).toHaveBeenCalledWith('Checkin');
});

test('checked in here: the bar says so instead of offering a check-in', async () => {
  native.getActiveCheckin.mockResolvedValue({
    checkin_id: 'c',
    building_id: 7,
    building_name: null,
    valid_until_ms: Date.now() + 74 * 60000 - 1000,
  });
  await show();
  expect(
    await screen.findByText("You're climbing here, 74 min left"),
  ).toBeTruthy();
  expect(screen.queryByText('Check in here')).toBeNull();
  native.getActiveCheckin.mockResolvedValue(null);
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
  await show();
  await screen.findByText(/^Owned by AC since /);
  standingsResult = () =>
    Promise.reject(new TypeError('Network request failed'));
  await flip({
    type: 'building_flipped',
    building_id: 7,
    from_team: 'AC',
    to_team: 'ETC',
    at: 'x',
  });
  expect(
    await screen.findByText(
      /^Last updated \d{1,2}[:.]\d{2}.*\. Can't reach the server\.$/,
    ),
  ).toBeTruthy();
  expect(screen.getByText(/^Owned by AC since /)).toBeTruthy();
});
