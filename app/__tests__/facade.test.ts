import {
  allocateWindows,
  describeStandings,
  facade,
  windowSlots,
} from '../src/standings/facade';

const team = (code: string, points: number) => ({ code, points });

describe('facade', () => {
  test('the same id draws the same building, within the ranges', () => {
    for (let id = 1; id <= 300; id++) {
      const f = facade(id);
      expect(facade(id)).toEqual(f);
      expect(f.floors).toBeGreaterThanOrEqual(4);
      expect(f.floors).toBeLessThanOrEqual(8);
      expect(f.bays).toBeGreaterThanOrEqual(3);
      expect(f.bays).toBeLessThanOrEqual(6);
    }
  });

  test('different ids give different buildings', () => {
    const shapes = new Set(
      Array.from({ length: 50 }, (_, i) => JSON.stringify(facade(i + 1))),
    );
    expect(shapes.size).toBeGreaterThan(30);
  });

  test('every slot but the door, ground floor first', () => {
    const f = { floors: 4, bays: 5, roof: 'gable', windows: 'tall' } as const;
    const slots = windowSlots(f);
    expect(slots).toHaveLength(4 * 5 - 1);
    expect(slots).not.toContainEqual({ floor: 0, bay: 2 });
    expect(slots[0]).toEqual({ floor: 0, bay: 0 });
  });
});

describe('allocateWindows', () => {
  const sizes = [1, 2, 3, 11, 19, 47];
  const cases = [
    [team('AC', 412), team('ETC', 280), team('MEC', 46)],
    [team('AC', 10000), team('B', 1), team('C', 1), team('D', 1)],
    [team('A', 1), team('B', 1)],
    Array.from({ length: 12 }, (_, i) => team(`T${i}`, 12 - i)),
  ];

  test.each(sizes)(
    'always fills exactly %i windows when teams have points',
    n => {
      for (const teams of cases) {
        expect(allocateWindows(teams, n, null)).toHaveLength(n);
      }
    },
  );

  test('every team with points gets a window while windows last', () => {
    const lit = allocateWindows(
      [team('AC', 10000), team('B', 1), team('C', 1), team('D', 0)],
      11,
      null,
    );
    expect(new Set(lit.map(t => t.code))).toEqual(new Set(['AC', 'B', 'C']));
  });

  test('more teams than windows: the top teams get one each', () => {
    const teams = Array.from({ length: 12 }, (_, i) => team(`T${i}`, 12 - i));
    expect(allocateWindows(teams, 3, null).map(t => t.code)).toEqual([
      'T0',
      'T1',
      'T2',
    ]);
  });

  test('shares follow points, most points first', () => {
    const lit = allocateWindows(
      [team('MEC', 46), team('AC', 412), team('ETC', 280)],
      19,
      null,
    );
    const count = (c: string) => lit.filter(t => t.code === c).length;
    expect(lit[0].code).toBe('AC');
    expect([count('AC'), count('ETC'), count('MEC')]).toEqual([11, 7, 1]);
  });

  test('a tie puts the owner first', () => {
    const tied = [team('AC', 310), team('ETC', 310)];
    expect(allocateWindows(tied, 10, 'ETC')[0].code).toBe('ETC');
    expect(allocateWindows(tied, 10, 'AC')[0].code).toBe('AC');
  });

  test('no points: nothing lit', () => {
    expect(allocateWindows([team('AC', 0)], 10, 'AC')).toEqual([]);
    expect(allocateWindows([], 10, null)).toEqual([]);
  });
});

test('the accessibility sentence', () => {
  expect(
    describeStandings(
      [team('AC', 41), team('ETC', 48), team('MEC', 11)],
      'ETC',
    ),
  ).toBe('Owned by ETC. ETC 48 percent, AC 41 percent, MEC 11 percent.');
  expect(describeStandings([], null)).toBe(
    'No team has points here in the last 7 days.',
  );
});
