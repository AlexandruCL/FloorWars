import { fireEvent, render, screen } from '@testing-library/react-native';
import { api, ApiError } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { FloorSensors } from '../src/native/floorSensors';
import { ordinal, RanksScreen } from '../src/screens/RanksScreen';

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
let stats: { rank: number | null; points: number };
const navigation = { navigate: jest.fn() };

beforeEach(() => {
  jest.clearAllMocks();
  clearReadCache();
  native.getActiveCheckin.mockResolvedValue(null);
  stats = { rank: 1, points: 120 };
  seasonsResult = async () => [
    { id: 3, starts_at: 'a', ends_at: 'b' },
    { id: 2, starts_at: 'a', ends_at: 'b' },
  ];
  boardResult = async () => ({
    scope: 'individual',
    season_id: 3,
    entries: [
      { rank: 1, id: 'u1', name: 'Ana', points: 120 },
      { rank: 2, id: 'u2', name: 'Ben', points: 80 },
    ],
  });
  apiMock.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/seasons/active':
        return { id: 3, starts_at: 'a', ends_at: '2026-12-07T00:00:00Z' };
      case '/seasons':
        return seasonsResult();
      case '/buildings':
        return BUILDINGS;
      case '/teams':
        return [
          { id: 1, code: 'AC', color_hex: '#1E88E5' },
          { id: 2, code: 'ETC', color_hex: '#E53935' },
        ];
      case '/me/season-stats':
        return { season_id: 3, team_id: 1, ...stats };
      default:
        return boardResult();
    }
  });
});

const show = (params?: object) =>
  render(
    <RanksScreen
      {...({ navigation, route: { key: 'r', name: 'Ranks', params } } as any)}
    />,
  );
const boardCalls = () =>
  apiMock.mock.calls.filter(c => c[1] === '/leaderboards').map(c => c[2].query);

test('defaults to Players in the active season, limit 50, your row marked', async () => {
  await show();
  expect(await screen.findByLabelText('1. Ana, you, 120 points')).toBeTruthy();
  expect(screen.getByLabelText('2. Ben, 80 points')).toBeTruthy();
  expect(screen.getByText('Season 3')).toBeTruthy();
  expect(boardCalls()).toEqual([
    { scope: 'individual', season_id: 3, limit: 50, building_id: undefined },
  ]);
});

test('outside the visible rows, your rank is pinned at the bottom', async () => {
  stats = { rank: 63, points: 12 };
  await show();
  expect(await screen.findByLabelText('You, 63rd, 12 points')).toBeTruthy();
});

test('the segments send the right scope and building_id', async () => {
  await show();
  await screen.findByLabelText(/^1\. Ana/);
  await fireEvent.press(screen.getByRole('tab', { name: 'Teams' }));
  await screen.findByLabelText(/^1\. Ana/);
  await fireEvent.press(screen.getByRole('tab', { name: 'In a building' }));
  expect(await screen.findByText('Alpha Tower')).toBeTruthy();
  await screen.findByLabelText(/^1\. Ana/);
  expect(boardCalls().map(q => [q.scope, q.building_id])).toEqual([
    ['individual', undefined],
    ['team', undefined],
    ['building', 4],
  ]);
});

test('team boards mark your team', async () => {
  boardResult = async () => ({
    scope: 'team',
    season_id: 3,
    entries: [
      { rank: 1, id: 'AC', name: 'AC', points: 4812 },
      { rank: 2, id: 'ETC', name: 'ETC', points: 4390 },
    ],
  });
  await show();
  await fireEvent.press(await screen.findByRole('tab', { name: 'Teams' }));
  expect(
    await screen.findByLabelText('1. AC, your team, 4,812 points'),
  ).toBeTruthy();
  expect(screen.getByLabelText('2. ETC, 4,390 points')).toBeTruthy();
});

test('the building defaults to the check-in building, else first by name', async () => {
  native.getActiveCheckin.mockResolvedValue({ building_id: 9 });
  await show();
  await fireEvent.press(
    await screen.findByRole('tab', { name: 'In a building' }),
  );
  expect(await screen.findByText('Zeta Hall')).toBeTruthy();
  await screen.findByLabelText(/^1\. Ana/);
  expect(boardCalls().pop().building_id).toBe(9);
});

test('the season sheet: the running season named, a choice reloads the board', async () => {
  await show();
  await fireEvent.press(
    await screen.findByRole('button', { name: 'Season 3. Change season' }),
  );
  expect(await screen.findByText('Running now')).toBeTruthy();
  await fireEvent.press(screen.getByText('Season 2'));
  expect(
    await screen.findByRole('button', { name: 'Season 2. Change season' }),
  ).toBeTruthy();
  await screen.findByLabelText(/^1\. Ana/);
  expect(boardCalls().pop().season_id).toBe(2);
});

test('without GET /seasons the sheet offers only the active season', async () => {
  seasonsResult = () => Promise.reject(new ApiError(404, {}));
  await show();
  await fireEvent.press(
    await screen.findByRole('button', { name: 'Season 3. Change season' }),
  );
  await screen.findByText('Running now');
  expect(screen.queryByText('Season 2')).toBeNull();
});

test('the building sheet switches the building board', async () => {
  await show();
  await fireEvent.press(
    await screen.findByRole('tab', { name: 'In a building' }),
  );
  await fireEvent.press(await screen.findByText('Alpha Tower'));
  await fireEvent.press(await screen.findByText('Zeta Hall'));
  await screen.findByLabelText(/^1\. Ana/);
  expect(boardCalls().pop().building_id).toBe(9);
});

test('empty and failure states', async () => {
  boardResult = async () => ({
    scope: 'individual',
    season_id: 3,
    entries: [],
  });
  await show();
  expect(
    await screen.findByText('No points on this board yet this season.'),
  ).toBeTruthy();
  await screen.unmount();

  clearReadCache();
  boardResult = () => Promise.reject(new TypeError('Network request failed'));
  await show();
  expect(
    await screen.findByText(
      "Can't reach the server. Check your connection, then pull down to retry.",
    ),
  ).toBeTruthy();
  await screen.unmount();

  clearReadCache();
  boardResult = () => Promise.reject(new ApiError(500, {}));
  await show();
  expect(
    await screen.findByText(
      'Something went wrong loading this. Pull down to retry.',
    ),
  ).toBeTruthy();
});

test('ordinals', () => {
  expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 63, 101, 111].map(ordinal)).toEqual([
    '1st',
    '2nd',
    '3rd',
    '4th',
    '11th',
    '12th',
    '13th',
    '21st',
    '22nd',
    '63rd',
    '101st',
    '111th',
  ]);
});
