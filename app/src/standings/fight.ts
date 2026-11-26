import { standingsOrder } from './facade';

type Scored = { code: string; points: number };

export const pointsText = (n: number) =>
  `${n.toLocaleString('en-US')} ${n === 1 ? 'point' : 'points'}`;

// One sentence on who holds a building and by how much (DESIGN.md section 10). When your team
// chases the owner, the sentence says what your team needs; otherwise it is the owner's lead.
export function fightLine(
  teams: Scored[],
  owner: string | null,
  mine: string | null = null,
): string {
  const list = standingsOrder(teams, owner);
  if (list.length === 0) {
    return 'No team has points here in the last 7 days. Climb the stairs to claim it.';
  }
  const holder = list.find(t => t.code === owner);
  if (!owner || !holder) {
    return 'Nobody owns it yet.';
  }
  const rival = list.find(t => t.code !== owner);
  if (!rival) {
    return `${owner} owns it. No other team has points here this week.`;
  }
  if (rival.points === holder.points) {
    return `Tied at ${pointsText(
      holder.points,
    )}. ${owner} keeps it until someone pulls ahead.`;
  }
  if (rival.points > holder.points) {
    return `${owner} owns it, but ${rival.code} leads by ${pointsText(
      rival.points - holder.points,
    )}.`;
  }
  const chaser = mine && mine !== owner && list.find(t => t.code === mine);
  if (chaser) {
    return `${owner} owns it. ${mine} needs ${pointsText(
      holder.points - chaser.points + 1,
    )} to take it.`;
  }
  return `${owner} owns it and leads ${rival.code} by ${pointsText(
    holder.points - rival.points,
  )}.`;
}

// The short owner line in the Buildings list: whose tag to show and what follows it.
export function ownerLine(
  teams: Scored[],
  owner: string | null,
): { code: string | null; text: string } {
  const list = standingsOrder(teams, owner);
  if (list.length === 0) {
    return { code: null, text: 'Open, no points this week' };
  }
  const top = list.find(t => t.code === owner) ?? list[0];
  const rival = list.find(t => t.code !== top.code);
  const n = (v: number) => v.toLocaleString('en-US');
  if (!rival) {
    return { code: top.code, text: 'only team with points' };
  }
  if (rival.points === top.points) {
    return {
      code: top.code,
      text: owner
        ? `tied at ${n(top.points)}, keeps it`
        : `tied at ${n(top.points)}`,
    };
  }
  if (rival.points > top.points) {
    return {
      code: top.code,
      text: `behind ${rival.code} by ${n(rival.points - top.points)}`,
    };
  }
  return { code: top.code, text: `leads by ${n(top.points - rival.points)}` };
}
