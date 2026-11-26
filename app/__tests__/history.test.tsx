import { fireEvent, render, screen } from '@testing-library/react-native';
import { api, ApiError } from '../src/api/client';
import { clearReadCache } from '../src/data/useRead';
import { reasonText } from '../src/history/reasons';
import { localMidnight, todayFigures, todayText } from '../src/history/today';
import { FloorSensors } from '../src/native/floorSensors';
import { HistoryScreen } from '../src/screens/HistoryScreen';
import { HomeScreen } from '../src/screens/HomeScreen';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const apiMock = api as unknown as jest.Mock;
const native = FloorSensors as unknown as Record<string, jest.Mock>;

const NOW = new Date(2026, 10, 17, 15, 30).getTime(); // local time on purpose
const MIDNIGHT = new Date(2026, 10, 17, 0, 0, 0, 0).getTime();
const seg = (over: Record<string, unknown> = {}) => ({
  id: String(Math.random()),
  checkin_id: 'c',
  started_at: new Date(NOW - 3600_000).toISOString(),
  building_id: 7,
  ascent_m: 3,
  duration_s: 20,
  vert_speed_mps: 0.15,
  steps: 18,
  stair_prob: 0.9,
  classifier_version: 'rules-1',
  status: 'verified',
  reason: null,
  steps_scored: 18,
  ...over,
});
const at = (ms: number) => new Date(ms).toISOString();
const page = (items: unknown[], next_cursor: string | null = null) => ({
  items,
  next_cursor,
});
const offline = () => Promise.reject(new TypeError('Network request failed'));

beforeEach(() => {
  jest.clearAllMocks();
  clearReadCache();
  jest.spyOn(Date, 'now').mockReturnValue(NOW);
});
afterEach(() => jest.restoreAllMocks());

describe('today figures', () => {
  test('local midnight', () => {
    expect(localMidnight(NOW)).toBe(MIDNIGHT);
  });

  test('00:00 today counts, 23:59 yesterday does not, paging stops at the first older item', async () => {
    const pages = jest
      .fn()
      .mockResolvedValueOnce(
        page(
          [
            seg({
              started_at: at(MIDNIGHT + 3600_000),
              steps_scored: 10,
              ascent_m: 1.25,
            }),
            seg({ started_at: at(MIDNIGHT), steps_scored: 5, ascent_m: 1.5 }),
          ],
          'p2',
        ),
      )
      .mockResolvedValueOnce(
        page(
          [
            seg({
              started_at: at(MIDNIGHT - 60_000),
              steps_scored: 99,
              ascent_m: 99,
            }),
            seg({ started_at: at(MIDNIGHT - 120_000), steps_scored: 99 }),
          ],
          'p3',
        ),
      );
    expect(await todayFigures(MIDNIGHT, pages)).toEqual({
      steps: 15,
      metres: 2.75,
    });
    expect(pages).toHaveBeenCalledTimes(2);
    expect(pages.mock.calls.map(c => c[0])).toEqual([undefined, 'p2']);
  });

  test('keeps paging while items are still today', async () => {
    const pages = jest
      .fn()
      .mockResolvedValueOnce(
        page([seg({ steps_scored: 1, ascent_m: 1 })], 'p2'),
      )
      .mockResolvedValueOnce(
        page([seg({ steps_scored: 2, ascent_m: 1 })], null),
      );
    expect(await todayFigures(MIDNIGHT, pages)).toEqual({
      steps: 3,
      metres: 2,
    });
  });

  test('only verified climbs count', async () => {
    const pages = jest.fn().mockResolvedValue(
      page([
        seg({ status: 'pending', steps_scored: 0, steps: 40, ascent_m: 9 }),
        seg({
          status: 'rejected',
          reason: 'speed',
          steps_scored: 0,
          steps: 40,
          ascent_m: 9,
        }),
        seg({ steps_scored: 7, ascent_m: 2 }),
      ]),
    );
    expect(await todayFigures(MIDNIGHT, pages)).toEqual({
      steps: 7,
      metres: 2,
    });
  });

  test('metres to one decimal', () => {
    expect(todayText({ steps: 12, metres: 3 })).toBe(
      'Verified today: 12 steps, 3.0 m',
    );
    expect(todayText({ steps: 0, metres: 2.349 })).toBe(
      'Verified today: 0 steps, 2.3 m',
    );
  });
});

describe('rejection reasons', () => {
  const known: [string, string][] = [
    [
      'pressure_steps_mismatch',
      "Your steps and the height you climbed didn't match, so it didn't count as stairs.",
    ],
    ['ascent_range', 'The climb was under 2 m or over 120 m.'],
    ['steps_range', 'The step count was outside what one climb can have.'],
    ['speed', 'The height changed faster or slower than walking up stairs.'],
    ['cadence', 'Your steps came faster or slower than walking pace.'],
    ['duration', 'The climb was too short or too long to count.'],
    [
      'rate_limit',
      'You reached the limit of counted steps for now. Later climbs count again.',
    ],
    [
      'no_checkin',
      "You weren't checked in when you climbed. Check in at the building first.",
    ],
    [
      'building_mismatch',
      "The climb didn't match the building you checked in at.",
    ],
    [
      'started_at_range',
      "The climb's time is more than 7 days old or in the future. Check your phone's clock.",
    ],
    ['season_inactive', 'No season was running when you climbed.'],
    ['no_team', "You hadn't joined a team this season when you climbed."],
    [
      'stair_prob_range',
      "The app sent a value the server didn't accept. That's an app bug, not you.",
    ],
    [
      'overlap',
      'This climb overlaps one that already counted, so it counted once.',
    ],
  ];
  test.each(known)('%s', (reason, text) => {
    expect(reasonText(reason)).toBe(text);
  });
  test('unknown and missing', () => {
    expect(reasonText('brand_new')).toBe('Not counted (reason: brand_new).');
    expect(reasonText(undefined)).toBe('Not counted.');
    expect(reasonText(null)).toBe('Not counted.');
    expect(reasonText('toString')).toBe('Not counted (reason: toString).');
  });
});

describe('History screen', () => {
  let segments: (cursor?: string) => Promise<unknown>;
  beforeEach(() => {
    apiMock.mockImplementation(async (_m: string, path: string, o: any) =>
      path === '/buildings'
        ? [{ id: 7, name: 'Library' }]
        : segments(o?.query?.cursor),
    );
  });

  test('rows show date, building, steps, ascent, status and the reason', async () => {
    segments = async () =>
      page([
        seg({ id: 'a' }),
        seg({ id: 'b', status: 'pending', steps_scored: 0, building_id: 99 }),
        seg({ id: 'c', status: 'rejected', reason: 'speed', steps_scored: 0 }),
        seg({
          id: 'd',
          status: 'rejected',
          reason: undefined,
          steps_scored: 0,
        }),
      ]);
    await render(<HistoryScreen />);
    expect(await screen.findAllByText('Library')).toHaveLength(3);
    expect(screen.getByText('Building 99')).toBeTruthy();
    expect(screen.getAllByText('18 steps, 3 m')).toHaveLength(4);
    expect(screen.getByText('Verified, 18 steps scored')).toBeTruthy();
    expect(screen.getByText('Pending')).toBeTruthy();
    expect(screen.getAllByText('Rejected')).toHaveLength(2);
    expect(
      screen.getByText(
        'The height changed faster or slower than walking up stairs.',
      ),
    ).toBeTruthy();
    expect(screen.getByText('Not counted.')).toBeTruthy();
    expect(apiMock).toHaveBeenCalledWith('get', '/me/segments', {
      query: { limit: 50, cursor: undefined },
    });
  });

  test('the next page loads at the end of the list, once', async () => {
    segments = async (cursor?: string) =>
      cursor
        ? page([seg({ id: 'z', building_id: 99 })])
        : page([seg({ id: 'a' })], 'p2');
    await render(<HistoryScreen />);
    await screen.findByText('Library');
    await fireEvent(screen.getByTestId('history-list'), 'endReached');
    expect(await screen.findByText('Building 99')).toBeTruthy();
    await fireEvent(screen.getByTestId('history-list'), 'endReached');
    const withCursor = apiMock.mock.calls.filter(c => c[2]?.query?.cursor);
    expect(withCursor).toHaveLength(1);
    expect(withCursor[0][2].query.cursor).toBe('p2');
  });

  test('empty, offline and error states', async () => {
    segments = async () => page([]);
    await render(<HistoryScreen />);
    expect(
      await screen.findByText(
        'No climbs yet. Check in at a building and take the stairs.',
      ),
    ).toBeTruthy();
    await screen.unmount();

    clearReadCache();
    segments = offline;
    await render(<HistoryScreen />);
    expect(
      await screen.findByText(
        "Can't reach the server. Check your connection, then pull down to retry.",
      ),
    ).toBeTruthy();
    await screen.unmount();

    clearReadCache();
    segments = () => Promise.reject(new ApiError(500, {}));
    await render(<HistoryScreen />);
    expect(
      await screen.findByText(
        'Something went wrong loading this. Pull down to retry.',
      ),
    ).toBeTruthy();
  });
});

describe('Home', () => {
  const navigation = {
    navigate: jest.fn(),
    addListener: jest.fn(() => () => {}),
  };
  let segments: () => Promise<unknown>;
  beforeEach(() => {
    native.getActiveCheckin.mockResolvedValue({
      checkin_id: 'c',
      building_id: 7,
      building_name: 'Library',
      valid_until_ms: NOW + 3600_000,
    });
    apiMock.mockImplementation(async () => segments());
  });
  const show = () => render(<HomeScreen {...({ navigation } as any)} />);

  test('loading', async () => {
    segments = () => new Promise(() => {});
    await show();
    expect(screen.getByText('Verified today: loading')).toBeTruthy();
  });

  test('the figures', async () => {
    segments = async () =>
      page([
        seg({ started_at: at(NOW - 1000), steps_scored: 12, ascent_m: 3 }),
        seg({ started_at: at(NOW - 2000), status: 'pending', steps_scored: 0 }),
        seg({ started_at: at(MIDNIGHT - 1000), steps_scored: 50 }),
      ]);
    await show();
    expect(
      await screen.findByText('Verified today: 12 steps, 3.0 m'),
    ).toBeTruthy();
  });

  test('unavailable with no cache', async () => {
    segments = offline;
    await show();
    expect(await screen.findByText('Verified today: unavailable')).toBeTruthy();
    expect(screen.queryByText(/Last updated/)).toBeNull();
  });

  test('unavailable with the cached value and its label', async () => {
    segments = async () => page([seg({ steps_scored: 12, ascent_m: 3 })]);
    await show();
    await screen.findByText('Verified today: 12 steps, 3.0 m');
    await screen.unmount();
    segments = offline;
    await show();
    expect(await screen.findByText('Verified today: unavailable')).toBeTruthy();
    expect(screen.getByText('Verified today: 12 steps, 3.0 m')).toBeTruthy();
    expect(
      screen.getByText(/^Last updated .+\. Can't reach the server\.$/),
    ).toBeTruthy();
  });

  test('standings button only with a check-in, and it opens Building', async () => {
    segments = async () => page([]);
    await show();
    await fireEvent.press(
      await screen.findByRole('button', { name: 'Building standings' }),
    );
    expect(navigation.navigate).toHaveBeenCalledWith('Building', {
      buildingId: 7,
    });
    await screen.unmount();

    native.getActiveCheckin.mockResolvedValue(null);
    await show();
    await screen.findByText('Verified today: 0 steps, 0.0 m');
    expect(
      screen.queryByRole('button', { name: 'Building standings' }),
    ).toBeNull();
  });
});
