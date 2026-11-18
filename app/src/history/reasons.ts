// Wording approved by Cristea (2026-11-17). Never shames elevator use.
const TEXT: Record<string, string> = {
  pressure_steps_mismatch:
    "Your steps and the height you climbed didn't match, so it didn't count as stairs.",
  ascent_range: 'The climb was under 2 m or over 120 m.',
  steps_range: 'The step count was outside what one climb can have.',
  speed: 'The height changed faster or slower than walking up stairs.',
  cadence: 'Your steps came faster or slower than walking pace.',
  duration: 'The climb was too short or too long to count.',
  rate_limit:
    'You reached the limit of counted steps for now. Later climbs count again.',
  no_checkin:
    "You weren't checked in when you climbed. Check in at the building first.",
  building_mismatch: "The climb didn't match the building you checked in at.",
  started_at_range:
    "The climb's time is more than 7 days old or in the future. Check your phone's clock.",
  season_inactive: 'No season was running when you climbed.',
  no_team: "You hadn't joined a team this season when you climbed.",
  stair_prob_range:
    "The app sent a value the server didn't accept. That's an app bug, not you.",
  overlap: 'This climb overlaps one that already counted, so it counted once.',
};

// reason missing: contract 0.8.0 is not deployed yet.
export function reasonText(reason: string | null | undefined): string {
  if (!reason) {
    return 'Not counted.';
  }
  return Object.hasOwn(TEXT, reason)
    ? TEXT[reason]
    : `Not counted (reason: ${reason}).`;
}
