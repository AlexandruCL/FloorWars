import { render, screen } from '@testing-library/react-native';
import { api } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { YouScreen } from '../src/screens/YouScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const navigation = { navigate: jest.fn() };
const seg = (id: string, status: string, steps: number) => ({
  id,
  building_id: 1,
  started_at: '2026-11-26T12:02:00Z',
  status,
  steps,
  steps_scored: status === 'verified' ? steps : 0,
  ascent_m: 12.4,
  reason: null,
});

beforeEach(() => {
  clearReadCache();
  apiMock.mockImplementation(async (_m: string, path: string) => {
    switch (path) {
      case '/seasons/active':
        return { id: 3, starts_at: '', ends_at: '2026-12-07T00:00:00Z' };
      case '/me/season-stats':
        return {
          season_id: 3,
          team_id: 1,
          steps_verified: 2300,
          points: 2204,
          rank: 14,
        };
      case '/teams':
        return [{ id: 1, code: 'AC', color_hex: '#1E88E5' }];
      case '/me/segments':
        return {
          items: [
            seg('a', 'pending', 52),
            seg('b', 'verified', 86),
            seg('c', 'rejected', 40),
            seg('d', 'verified', 10),
          ],
          next_cursor: null,
        };
    }
    throw new Error(path);
  });
});

test('your team, season figures and the last three climbs', async () => {
  await render(<YouScreen {...({ navigation } as any)} />);
  expect(await screen.findByText('You climb for AC')).toBeTruthy();
  expect(screen.getByText('115')).toBeTruthy(); // 2300 steps / 20
  expect(screen.getByText('2,204')).toBeTruthy();
  expect(screen.getByText('14th')).toBeTruthy();
  expect(await screen.findByText('Pending')).toBeTruthy();
  expect(screen.getByText('Counted')).toBeTruthy();
  expect(screen.getByText('Not counted')).toBeTruthy();
  expect(screen.getByText('86 steps, 12.4 m up')).toBeTruthy();
  expect(screen.queryByText('10 steps, 12.4 m up')).toBeNull(); // only three
  expect(screen.getByText('All climbs')).toBeTruthy();
});
