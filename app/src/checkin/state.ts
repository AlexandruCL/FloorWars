import { ApiError } from '../api/client';
import type { components } from '../api/schema';
import { DeviceError } from './deps';

export type Method = 'qr' | 'geofence';
export type Checkin = components['schemas']['Checkin'];
export type ErrorKind =
  | 'expired'
  | 'rejected'
  | 'outside'
  | 'denied'
  | 'unavailable'
  | 'failed';

export type Phase =
  | { name: 'idle' }
  | { name: 'scanning' }
  | { name: 'locating' }
  | { name: 'submitting' }
  | { name: 'success'; checkin: Checkin; building: string }
  | { name: 'error'; kind: ErrorKind; method: Method };

// Problem.type values the server sends on 403/503 (server/README.md, "Check-in").
const BY_PROBLEM_TYPE: Record<string, ErrorKind> = {
  'urn:floorwars:problem:qr-expired': 'expired',
  'urn:floorwars:problem:qr-not-yet-valid': 'expired',
  'urn:floorwars:problem:qr-malformed': 'rejected',
  'urn:floorwars:problem:qr-invalid': 'rejected',
  'urn:floorwars:problem:building-unknown': 'rejected',
  'urn:floorwars:problem:qr-unavailable': 'unavailable',
  'urn:floorwars:problem:outside-geofence': 'outside',
  'urn:floorwars:problem:location-inaccurate': 'outside',
};

// Reads status and Problem.type, never Problem.detail or title.
export function errorKind(e: unknown, method: Method): ErrorKind {
  if (e instanceof DeviceError) {
    return e.kind;
  }
  if (!(e instanceof ApiError)) {
    return 'failed';
  }
  const type = (e.problem as { type?: unknown } | undefined)?.type;
  if (typeof type === 'string' && type in BY_PROBLEM_TYPE) {
    return BY_PROBLEM_TYPE[type];
  }
  // A 403 without a known type: the contract only says the token or the position was refused.
  if (e.status === 403) {
    return method === 'qr' ? 'rejected' : 'outside';
  }
  return 'failed';
}

// Every message ends with the next step.
export function errorMessage(kind: ErrorKind, method: Method): string {
  switch (kind) {
    case 'expired':
      return 'This code has expired. Scan the code at the entrance again, or use your location.';
    case 'rejected':
      return 'This code was not accepted. Scan the code at the building entrance, or use your location.';
    case 'outside':
      return 'You are not close enough to a building. Walk to the entrance and try again, or scan the entrance code.';
    case 'denied':
      return method === 'qr'
        ? 'Camera access is off. Allow it in Settings, or check in with your location.'
        : 'Location access is off. Allow it in Settings, or scan the entrance code.';
    case 'unavailable':
      return method === 'qr'
        ? 'Scanning is not available right now. Check in with your location.'
        : 'Your location is not available. Go outside or near a window and try again, or scan the entrance code.';
    default:
      return 'Could not check in. Check your connection, wait a moment, and try again.';
  }
}

export function minutesLeft(c: Checkin, nowMs = Date.now()): number {
  const total = Date.parse(c.valid_until) - Date.parse(c.valid_from);
  // Capped at the validity length so a wrong phone clock cannot show more than the server granted.
  const left = Math.min(Date.parse(c.valid_until) - nowMs, total);
  return Math.max(0, Math.ceil(left / 60000));
}

export function successText(
  building: string,
  c: Checkin,
  nowMs = Date.now(),
): string {
  return `Checked in: ${building}, ${minutesLeft(c, nowMs)} min left`;
}
