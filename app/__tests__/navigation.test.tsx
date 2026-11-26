import { fireEvent, render, screen } from '@testing-library/react-native';
import { api } from '../src/api/client';
import { markOnboardingSeen } from '../src/auth/session';
import { clearReadCache } from '../src/data/useRead';
import { linking, RootNavigator } from '../src/navigation/RootNavigator';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;

let buildings: unknown[];

beforeEach(async () => {
  jest.clearAllMocks();
  clearReadCache();
  await markOnboardingSeen();
  buildings = [
    { id: 9, name: 'Zeta Hall' },
    { id: 4, name: 'Alpha Tower' },
  ];
  apiMock.mockImplementation(async (_m: string, path: string) => {
    if (path === '/buildings') {
      return buildings;
    }
    if (path === '/buildings/{id}/standings') {
      return { building_id: 4, season_id: 1, owner: null, teams: [] };
    }
    throw new TypeError('Network request failed');
  });
});

test('four tabs, Climb first', async () => {
  await render(<RootNavigator isSignedIn />);
  await screen.findAllByText('Climb');
  for (const tab of ['Climb', 'Buildings', 'Ranks', 'You']) {
    expect(screen.getByText(tab)).toBeTruthy();
  }
});

test('Buildings lists every building by name and a row opens Building', async () => {
  await render(<RootNavigator isSignedIn />);
  await fireEvent.press(await screen.findByText('Buildings'));
  const alpha = await screen.findByRole('button', { name: 'Alpha Tower' });
  const zeta = screen.getByRole('button', { name: 'Zeta Hall' });
  // Sorted by name: Alpha before Zeta although the API sent Zeta first.
  const order = screen
    .getAllByRole('button')
    .filter(b => b === alpha || b === zeta);
  expect(order).toEqual([alpha, zeta]);
  await fireEvent.press(alpha);
  expect(
    await screen.findByText('No team has points here in the last 7 days.', {
      exact: false,
    }),
  ).toBeTruthy();
});

test('Buildings says so when none are set up', async () => {
  buildings = [];
  await render(<RootNavigator isSignedIn />);
  await fireEvent.press(await screen.findByText('Buildings'));
  expect(
    await screen.findByText('No buildings are set up for this season yet.'),
  ).toBeTruthy();
});

test('You holds the rows that left Home', async () => {
  await render(<RootNavigator isSignedIn />);
  await fireEvent.press(await screen.findByText('You'));
  for (const row of [
    'All climbs',
    'How FloorWars works',
    'Sensor logger',
    'Sign out',
  ]) {
    expect(await screen.findByText(row)).toBeTruthy();
  }
});

test('a building link opens Building on top of the Buildings tab', () => {
  const state = linking.getStateFromPath!('building/7', linking.config);
  expect(state).toEqual({
    routes: [
      {
        name: 'Main',
        state: {
          routes: [
            { name: 'Tabs', state: { routes: [{ name: 'Buildings' }] } },
            expect.objectContaining({
              name: 'Building',
              params: { buildingId: 7 },
            }),
          ],
        },
      },
    ],
  });
});

test('other links are left alone', () => {
  expect(linking.getStateFromPath!('nowhere', linking.config)).toBeUndefined();
});
