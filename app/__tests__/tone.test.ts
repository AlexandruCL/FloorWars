import { contrast, teamTone } from '../src/ui/tone';

// The samples from DESIGN.md section 5, checked on the design canvas.
const samples: [string, string][] = [
  ['#1E88E5', '#3095F3'],
  ['#E53935', '#E86156'],
  ['#F9A825', '#F9A825'],
  ['#112233', '#8095AA'],
  ['#000000', '#868686'],
  ['#FFFFFF', '#DEDEDE'],
];

const channels = (hex: string) =>
  [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));

test.each(samples)('%s becomes about %s with night text', (from, to) => {
  const { tone, ink } = teamTone(from);
  // One step per channel of rounding slack between the canvas and this code.
  channels(tone).forEach((c, i) =>
    expect(Math.abs(c - channels(to)[i])).toBeLessThanOrEqual(1),
  );
  expect(ink).toBe('#0A0E16');
});

test('text on every tone passes 4.5:1', () => {
  for (const hex of ['#000000', '#FFFFFF', '#00FF00', '#0000FF', '#FF00FF']) {
    const { tone, ink } = teamTone(hex);
    expect(contrast(tone, ink)).toBeGreaterThanOrEqual(4.5);
  }
});

test('a malformed colour still gives a drawable grey', () => {
  expect(teamTone('red').tone).toMatch(/^#[0-9A-F]{6}$/);
});
