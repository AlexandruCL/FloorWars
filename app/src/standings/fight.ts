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
