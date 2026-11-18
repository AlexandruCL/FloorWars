export type BarSegment = {
  code: string;
  color: string;
  x: number; // percent of the bar width
  width: number;
};

// One segment per team with points, each as its share of all points, in the order given.
export function barSegments(
  teams: { code: string; color_hex: string; points: number }[],
): BarSegment[] {
  const total = teams.reduce((n, t) => n + Math.max(0, t.points), 0);
  if (total <= 0) {
    return [];
  }
  let x = 0;
  return teams
    .filter(t => t.points > 0)
    .map(t => {
      const width = (t.points / total) * 100;
      const seg = { code: t.code, color: t.color_hex, x, width };
      x += width;
      return seg;
    });
}
