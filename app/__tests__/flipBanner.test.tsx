import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { api } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { FlipBanner } from '../src/realtime/FlipBanner';
import { useGameEvents } from '../src/realtime/useGameEvents';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
jest.mock('../src/realtime/useGameEvents', () => ({
  useGameEvents: jest.fn(),
}));
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useNavigation: () => ({ navigate: mockNavigate }),
}));
const hook = useGameEvents as jest.Mock;
const flip = (e: object) =>
  act(() => hook.mock.calls[hook.mock.calls.length - 1][0](e));

beforeEach(() => {
  jest.useFakeTimers();
  clearReadCache();
  (api as unknown as jest.Mock).mockImplementation(
    async (_m: string, path: string) => {
      switch (path) {
        case '/buildings':
          return [{ id: 7, name: 'Faculty of Mechanical Engineering' }];
        case '/teams':
          return [
            { id: 1, code: 'AC', color_hex: '#1E88E5' },
            { id: 2, code: 'ETC', color_hex: '#E53935' },
          ];
        case '/seasons/active':
          return { id: 3, starts_at: '', ends_at: '' };
        case '/me/season-stats':
          return { season_id: 3, team_id: 1 };
      }
      throw new Error(path);
    },
  );
});
afterEach(() => jest.useRealTimers());

const event = {
  type: 'building_flipped',
  building_id: 7,
  from_team: 'AC',
  to_team: 'ETC',
  at: 'x',
};

test('a flip shows who took which building and opens it on tap', async () => {
  await render(<FlipBanner />);
  await act(async () => {});
  await flip(event);
  expect(
    await screen.findByText('ETC took Faculty of Mechanical Engineering'),
  ).toBeTruthy();
  expect(
    screen.getByText('Your team lost it. Tap to see the standings.'),
  ).toBeTruthy();
  await fireEvent.press(screen.getByRole('button'));
  expect(mockNavigate).toHaveBeenCalledWith('Main', {
    screen: 'Building',
    params: { buildingId: 7 },
  });
});

test('another team losing it has no loss line, and the banner leaves after 5 s', async () => {
  await render(<FlipBanner />);
  await act(async () => {});
  await flip({ ...event, from_team: null });
  await screen.findByText('ETC took Faculty of Mechanical Engineering');
  expect(screen.queryByText(/Your team lost it/)).toBeNull();
  await act(async () => {
    jest.advanceTimersByTime(6000);
  });
  expect(screen.queryByText(/took Faculty/)).toBeNull();
});
