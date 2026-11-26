import { act, render, screen } from '@testing-library/react-native';
import { api } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { FloorSensors } from '../src/native/floorSensors';
import { HomeScreen } from '../src/screens/HomeScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
// Record what each drawing was asked to replay.
const replays: unknown[] = [];
jest.mock('../src/standings/BuildingDrawing', () => ({
  BuildingDrawing: (p: { replay?: unknown; unlit?: boolean }) => {
    if (!p.unlit) {
      replays.push(p.replay ?? null);
    }
    return null;
  },
}));
const native = FloorSensors as unknown as Record<string, jest.Mock>;
const listeners: (() => void)[] = [];
const navigation = {
  navigate: jest.fn(),
  addListener: jest.fn((_e: string, fn: () => void) => {
    listeners.push(fn);
    return () => {};
  }),
};
const checkin = (id: string) => ({
  checkin_id: id,
  building_id: 1,
  building_name: 'Tower',
  valid_until_ms: Date.now() + 3600_000,
});

beforeEach(() => {
  clearReadCache();
  replays.length = 0;
  (api as unknown as jest.Mock).mockRejectedValue(new TypeError('offline'));
});

test('an existing check-in does not replay; a new one lights up', async () => {
  native.getActiveCheckin.mockResolvedValue(checkin('a'));
  await render(<HomeScreen {...({ navigation } as any)} />);
  await screen.findByText('Tower');
  expect(replays.every(r => r === null)).toBe(true);

  native.getActiveCheckin.mockResolvedValue(checkin('b'));
  await act(async () => listeners.forEach(fn => fn()));
  await act(async () => {});
  expect(replays[replays.length - 1]).toMatchObject({
    kind: 'checkin',
    from: [],
  });
});
