import { api } from '../api/client';
import type { components } from '../api/schema';
import { useRead } from './useRead';

type Season = components['schemas']['Season'];
type SeasonStats = components['schemas']['SeasonStats'];
type Team = components['schemas']['Team'];

export type Me = { season: Season; stats: SeasonStats; team: Team | null };

// The active season, your stats in it and your team; shared by Climb, You and the accent colour.
export function fetchMe(): Promise<Me> {
  return Promise.all([
    api('get', '/seasons/active'),
    api('get', '/me/season-stats'),
    api('get', '/teams'),
  ]).then(([season, stats, teams]) => ({
    season,
    stats,
    team: teams.find(t => t.id === stats.team_id) ?? null,
  }));
}

export const useMe = () => useRead('me', fetchMe);

// "Season 3, ends Sunday" within a week, "Season 3, ends 30 November" further out. A season that
// ends at midnight ends on the day before.
export function seasonText(season: Season, now = Date.now()): string {
  const end = new Date(Date.parse(season.ends_at) - 1);
  const soon = end.getTime() - now < 7 * 24 * 3600 * 1000;
  const when = soon
    ? end.toLocaleDateString('en-GB', { weekday: 'long' })
    : end.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' });
  return `Season ${season.id}, ends ${when}`;
}
