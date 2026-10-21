// Display-only floor-equivalent (IMPLEMENTATION_PLAN.md section 2). An estimate from verified
// steps, never a storey number and never from building floor data. Nothing stores floors: the API
// returns steps and the UI converts at render time.

// About 6 steps per metre times a 3.3 m storey. Tunable after real recordings.
export const STEPS_PER_FLOOR_EQUIVALENT = 20;

// Every screen that shows the number shows this label next to it.
export const FLOOR_EQUIVALENT_LABEL = 'floors (estimate)';

// Whole floor-equivalents, rounded down: 200 steps is 10, 19 steps is 0.
export function floorEquivalent(verifiedSteps: number): number {
  return Math.floor(Math.max(0, verifiedSteps) / STEPS_PER_FLOOR_EQUIVALENT);
}
