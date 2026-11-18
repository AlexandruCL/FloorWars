import { fireEvent, render, screen } from '@testing-library/react-native';
import { api, ApiError } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { FloorSensors } from '../src/native/floorSensors';
import { LeaderboardsScreen } from '../src/screens/LeaderboardsScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const native = FloorSensors as unknown as Record<string, jest.Mock>;

const BUILDINGS = [
  { id: 9, name: 'Zeta Hall' },
  { id: 4, name: 'Alpha Tower' },
];
let seasonsResult: () => Promise<unknown>;
let boardResult: () => Promise<unknown>;

beforeEach(() => {
  jest.clearAllMocks();
  clearReadCache();
  native.getActiveCheckin.mockResolvedValue(null);
  seasonsResult = async () => [
    { id: 3, starts_at: 'a', ends_at: 'b' },
    { id: 2, starts_at: 'a', ends_at: 'b' },
  ];
  boardResult = async () => ({
    scope: 'individual',
    season_id: 3,
    entries: [{ rank: 1, id: 'u1', name: 'Ana', points: 120 }],
  });
  apiMock.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/seasons/active':
        return { id: 3, starts_at: 'a', ends_at: 'b' };
      case '/seasons':
        return seasonsResult();
      case '/buildings':
        return BUILDINGS;
      default:
        return boardResult();
    }
  });
});

const boardCalls = () =>
  apiMock.mock.calls.filter(c => c[1] === '/leaderboards').map(c => c[2].query);
const selected = (name: string) =>
  screen.getByRole('radio', { name }).props.accessibilityState.selected;

test('defaults to the active season and the individual board, limit 50', async () => {
  await render(<LeaderboardsScreen />);
  expect(await screen.findByLabelText('1. Ana, 120 points')).toBeTruthy();
  expect(selected('Season 3')).toBe(true);
  expect(boardCalls()).toEqual([
    { scope: 'individual', season_id: 3, limit: 50, building_id: undefined },
  ]);
});

test('tabs send the right scope and building_id', async () => {
  await render(<LeaderboardsScreen />);
  await screen.findByLabelText('1. Ana, 120 points');
  await fireEvent.press(screen.getByRole('tab', { name: 'Team' }));
  await screen.findByLabelText('1. Ana, 120 points');
  await fireEvent.press(screen.getByRole('tab', { name: 'Building' }));
  await screen.findByRole('radio', { name: 'Alpha Tower' });
  await screen.findByText('1');
  expect(boardCalls().map(q => [q.scope, q.building_id])).toEqual([
    ['individual', undefined],
    ['team', undefined],
    ['building', 4],
  ]);
  await fireEvent.press(screen.getByRole('radio', { name: 'Zeta Hall' }));
  await screen.findByText('1');
  expect(boardCalls().pop().building_id).toBe(9);
});

test('building picker defaults to the check-in building, else first by name', async () => {
  native.getActiveCheckin.mockResolvedValue({ building_id: 9 });
  await render(<LeaderboardsScreen />);
  await fireEvent.press(await screen.findByRole('tab', { name: 'Building' }));
  await screen.findByRole('radio', { name: 'Zeta Hall' });
  await screen.findByText('1');
  expect(boardCalls().pop().building_id).toBe(9);
  expect(
    screen.getByRole('radio', { name: 'Zeta Hall' }).props.accessibilityState
      .selected,
  ).toBe(true);
});

test('without GET /seasons the selector shows only the active season', async () => {
  seasonsResult = () => Promise.reject(new ApiError(404, {}));
  await render(<LeaderboardsScreen />);
  await screen.findByLabelText('1. Ana, 120 points');
  expect(
    screen.getAllByRole('radio').map(n => n.props.accessibilityLabel ?? ''),
  ).toHaveLength(1);
  expect(selected('Season 3')).toBe(true);
});

test('choosing another season asks for it', async () => {
  await render(<LeaderboardsScreen />);
  await screen.findByLabelText('1. Ana, 120 points');
  await fireEvent.press(screen.getByRole('radio', { name: 'Season 2' }));
  await screen.findByLabelText('1. Ana, 120 points');
  expect(boardCalls().pop().season_id).toBe(2);
});

test('empty and failure states', async () => {
  boardResult = async () => ({
    scope: 'individual',
    season_id: 3,
    entries: [],
  });
  await render(<LeaderboardsScreen />);
  expect(
    await screen.findByText('No points on this board yet this season.'),
  ).toBeTruthy();
  await screen.unmount();

  clearReadCache();
  boardResult = () => Promise.reject(new TypeError('Network request failed'));
  await render(<LeaderboardsScreen />);
  expect(
    await screen.findByText(
      "Can't reach the server. Check your connection, then pull down to retry.",
    ),
  ).toBeTruthy();
  await screen.unmount();

  clearReadCache();
  boardResult = () => Promise.reject(new ApiError(500, {}));
  await render(<LeaderboardsScreen />);
  expect(
    await screen.findByText(
      'Something went wrong loading this. Pull down to retry.',
    ),
  ).toBeTruthy();
});
