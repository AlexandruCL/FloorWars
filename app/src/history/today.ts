import { api } from '../api/client';
import type { components } from '../api/schema';

export type SegmentRecord = components['schemas']['SegmentRecord'];
export type SegmentPage = components['schemas']['SegmentPage'];
export const PAGE_SIZE = 50;

export function fetchSegmentPage(cursor?: string): Promise<SegmentPage> {
  return api('get', '/me/segments', { query: { limit: PAGE_SIZE, cursor } });
}

export function localMidnight(now: number): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

// Verified steps and ascent since local midnight. Pages run newest first, so paging stops at the
// first item older than midnight. Pending and rejected climbs are not counted.
export async function todayFigures(
  midnight: number,
  page: (cursor?: string) => Promise<SegmentPage> = fetchSegmentPage,
): Promise<{ steps: number; metres: number }> {
  let steps = 0;
  let metres = 0;
  let cursor: string | undefined;
  for (;;) {
    const p = await page(cursor);
    for (const s of p.items) {
      if (Date.parse(s.started_at) < midnight) {
        return { steps, metres };
      }
      if (s.status === 'verified') {
        steps += s.steps_scored;
        metres += s.ascent_m;
      }
    }
    if (!p.next_cursor) {
      return { steps, metres };
    }
    cursor = p.next_cursor;
  }
}

export function todayText(f: { steps: number; metres: number }): string {
  return `Verified today: ${f.steps} steps, ${f.metres.toFixed(1)} m`;
}
