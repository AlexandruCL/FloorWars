import { seasonText } from '../src/data/myTeam';
import { fightLine, pointsText } from '../src/standings/fight';

const AC = { code: 'AC', points: 412 };
const ETC = { code: 'ETC', points: 280 };

test('the owner leads', () => {
  expect(fightLine([ETC, AC], 'AC')).toBe(
    'AC owns it and leads ETC by 132 points.',
  );
});

test('your team chases the owner', () => {
  expect(fightLine([AC, ETC], 'AC', 'ETC')).toBe(
    'AC owns it. ETC needs 133 points to take it.',
  );
  // Your team with no points here gets the owner's lead instead.
  expect(fightLine([AC, ETC], 'AC', 'MEC')).toBe(
    'AC owns it and leads ETC by 132 points.',
  );
});

test('a tie keeps the owner', () => {
  expect(
    fightLine(
      [
        { code: 'AC', points: 310 },
        { code: 'ETC', points: 310 },
      ],
      'ETC',
    ),
  ).toBe('Tied at 310 points. ETC keeps it until someone pulls ahead.');
});

test('nobody, alone, and an owner that fell behind', () => {
  expect(fightLine([AC], null)).toBe('Nobody owns it yet.');
  expect(fightLine([], 'AC')).toBe('Nobody owns it yet.');
  expect(fightLine([AC], 'AC')).toBe(
    'AC owns it. No other team has points here this week.',
  );
  expect(fightLine([AC, ETC], 'ETC')).toBe(
    'ETC owns it, but AC leads by 132 points.',
  );
});

test('points are counted in words and grouped', () => {
  expect(pointsText(1)).toBe('1 point');
  expect(pointsText(0)).toBe('0 points');
  expect(pointsText(12480)).toBe('12,480 points');
});

test('season end as a weekday this week, as a date later', () => {
  const now = Date.parse('2026-11-26T12:00:00Z');
  const season = (ends_at: string) => ({ id: 3, starts_at: '', ends_at });
  expect(seasonText(season('2026-11-30T00:00:00Z'), now)).toMatch(
    /^Season 3, ends (Sunday|Monday)$/,
  );
  expect(seasonText(season('2026-12-14T00:00:00Z'), now)).toMatch(
    /^Season 3, ends 1[34] December$/,
  );
});
