import {
  FLOOR_EQUIVALENT_LABEL,
  STEPS_PER_FLOOR_EQUIVALENT,
  floorEquivalent,
} from '../src/scoring/floorEquivalent';

test('20 verified steps make one floor-equivalent', () => {
  expect(STEPS_PER_FLOOR_EQUIVALENT).toBe(20);
  expect(floorEquivalent(200)).toBe(10);
});

test('rounds down to whole floors: 19 steps is 0, 39 steps is 1', () => {
  expect(floorEquivalent(19)).toBe(0);
  expect(floorEquivalent(20)).toBe(1);
  expect(floorEquivalent(39)).toBe(1);
});

test('no steps or a negative count gives 0', () => {
  expect(floorEquivalent(0)).toBe(0);
  expect(floorEquivalent(-5)).toBe(0);
});

test('the display label marks it as an estimate', () => {
  expect(FLOOR_EQUIVALENT_LABEL).toBe('floors (estimate)');
});
