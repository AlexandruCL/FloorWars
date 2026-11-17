import { api, ApiError } from '../api/client';
import { DEV_FORCE_NO_BAROMETER } from '../config/devFlags';
import type { FloorSensorsStatus } from '../native/NativeFloorSensors';
import { notifyFlips } from '../sync/syncWorker';

export const LANDING_SCAN_COOLDOWN_MS = 600_000;
const MAX_TOKEN_LEN = 512;
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;

// Unknown status counts as "has one": the fallback only replaces detection when we are sure.
export function hasBarometer(status: FloorSensorsStatus | null): boolean {
  if (__DEV__ && DEV_FORCE_NO_BAROMETER) {
    return false;
  }
  return status?.has_barometer ?? true;
}

// The sticker format is Ionut's and undefined: only length and control characters are checked.
export function tokenOk(raw: string): boolean {
  return raw.length > 0 && raw.length <= MAX_TOKEN_LEN && !CONTROL.test(raw);
}

// In memory per building, as decided: an app restart clears it and the server limit still applies.
const until = new Map<number, number>();
export const cooldownMsLeft = (building: number, now = Date.now()) =>
  Math.max(0, (until.get(building) ?? 0) - now);
export const resetCooldownsForTests = () => until.clear();

const min = (ms: number) => Math.ceil(ms / 60000);
const INVALID = "This code isn't a FloorWars stair sticker.";

export type ScanResult = {
  kind: 'ok' | 'cooldown' | 'forbidden' | 'tooMany' | 'invalid' | 'offline';
  text: string;
};

export async function submitLandingScan(
  buildingId: number,
  raw: string,
  now = Date.now(),
): Promise<ScanResult> {
  const left = cooldownMsLeft(buildingId, now);
  if (left > 0) {
    return {
      kind: 'cooldown',
      text: `You can scan again in this building in ${min(left)} min.`,
    };
  }
  if (!tokenOk(raw)) {
    return { kind: 'invalid', text: INVALID };
  }
  try {
    const scan = await api('post', '/landing-scans', {
      body: {
        qr_token: raw,
        building_id: buildingId,
        scanned_at: new Date(now).toISOString(),
      },
    });
    until.set(buildingId, now + LANDING_SCAN_COOLDOWN_MS);
    if (scan.flips?.length) {
      notifyFlips(scan.flips);
    }
    return {
      kind: 'ok',
      text:
        scan.points == null
          ? 'Scan counted.'
          : `Scan counted: +${scan.points} points.`,
    };
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 403) {
        return {
          kind: 'forbidden',
          text: "This sticker isn't for this building, or it has expired.",
        };
      }
      if (e.status === 422) {
        return { kind: 'invalid', text: INVALID };
      }
      if (e.status === 429) {
        // No Retry-After header: the full cooldown (Cristea's decision, 2026-11-17).
        const ms =
          e.retryAfterS == null
            ? LANDING_SCAN_COOLDOWN_MS
            : e.retryAfterS * 1000;
        until.set(buildingId, now + ms);
        return {
          kind: 'tooMany',
          text: `Too many scans. Try again in ${min(ms)} min.`,
        };
      }
    }
    return {
      kind: 'offline',
      text: "Couldn't send the scan. Check your connection and try again.",
    };
  }
}
