// The building drawing's data (DESIGN.md section 9). Buildings have no geometry in the API, so
// each one gets a facade seeded from its id: the same id always draws the same building.

export type Roof = 'parapet' | 'stairL' | 'stairR' | 'gable';
export type WindowShape = 'tall' | 'square' | 'wide';
export type Facade = {
  floors: number; // 4 to 8
  bays: number; // 3 to 6
  roof: Roof;
  windows: WindowShape;
};

// Hash the id, then mulberry32, so neighbouring ids look different (the canvas code).
function seeded(id: number): () => number {
  /* eslint-disable no-bitwise */
  let h = id >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h ^= h >>> 16;
  return () => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  /* eslint-enable no-bitwise */
}

export function facade(id: number): Facade {
  const rnd = seeded(id);
  const pick = <T>(list: T[]) => list[Math.floor(rnd() * list.length)];
  return {
    floors: 4 + Math.floor(rnd() * 5),
    bays: 3 + Math.floor(rnd() * 4),
    roof: pick<Roof>(['parapet', 'stairL', 'stairR', 'gable']),
    windows: pick<WindowShape>(['tall', 'square', 'wide']),
  };
}

// The door replaces the middle ground-floor window.
export const doorBay = (f: Facade) => Math.floor(f.bays / 2);

// Window slots from the ground floor up, left to right, skipping the door.
export function windowSlots(f: Facade): { floor: number; bay: number }[] {
  const slots = [];
  for (let floor = 0; floor < f.floors; floor++) {
    for (let bay = 0; bay < f.bays; bay++) {
      if (floor !== 0 || bay !== doorBay(f)) {
        slots.push({ floor, bay });
      }
    }
  }
  return slots;
}

type Scored = { code: string; points: number };

// Teams with points, most first; on a tie the owner first, because the owner keeps a building
// on a tie.
export function standingsOrder<T extends Scored>(
  teams: T[],
  owner: string | null,
): T[] {
  return teams
    .filter(t => t.points > 0)
    .sort(
      (a, b) =>
        b.points - a.points ||
        (a.code === owner ? -1 : b.code === owner ? 1 : 0),
    );
}

// One team per lit window, in fill order. Each team with points gets windows in proportion to
// its share (largest remainder) and at least one; with more teams than windows the top teams
// get one each and the rest stay in the table.
export function allocateWindows<T extends Scored>(
  teams: T[],
  count: number,
  owner: string | null,
): T[] {
  const list = standingsOrder(teams, owner);
  if (list.length === 0 || count <= 0) {
    return [];
  }
  if (list.length >= count) {
    return list.slice(0, count);
  }
  const total = list.reduce((s, t) => s + t.points, 0);
  const shares = list.map(t => {
    const q = (t.points / total) * count;
    return { t, q, k: Math.max(1, Math.floor(q)) };
  });
  let sum = shares.reduce((s, x) => s + x.k, 0);
  // The one-window minimum can overshoot: take back from whoever is most over its share.
  while (sum > count) {
    const x = shares
      .filter(y => y.k > 1)
      .sort((u, v) => v.k - v.q - (u.k - u.q))[0];
    x.k -= 1;
    sum -= 1;
  }
  while (sum < count) {
    const x = [...shares].sort((u, v) => v.q - v.k - (u.q - u.k))[0];
    x.k += 1;
    sum += 1;
  }
  return shares.flatMap(x => Array<T>(x.k).fill(x.t));
}

// "Owned by ETC. ETC 48 percent, AC 41 percent, MEC 11 percent."
export function describeStandings(
  teams: Scored[],
  owner: string | null,
): string {
  const list = standingsOrder(teams, owner);
  if (list.length === 0) {
    return 'No team has points here in the last 7 days.';
  }
  const total = list.reduce((s, t) => s + t.points, 0);
  const parts = list.map(
    t => `${t.code} ${Math.round((t.points / total) * 100)} percent`,
  );
  return `${owner ? `Owned by ${owner}.` : 'Nobody owns it yet.'} ${parts.join(
    ', ',
  )}.`;
}
