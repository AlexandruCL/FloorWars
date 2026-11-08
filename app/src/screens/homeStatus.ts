import type { ActiveCheckin } from '../native/NativeFloorSensors';
import type { SyncState } from '../sync/syncWorker';

// Same rule as the check-in screen: round up, never below zero. The phone clock is all we have
// here, there is no valid_from to cap against.
export function minutesLeftMs(c: ActiveCheckin, nowMs: number): number {
  return Math.max(0, Math.ceil((c.valid_until_ms - nowMs) / 60000));
}

// Android only, and only when the app is known not to be exempt. Unknown (null) shows nothing.
export function showBatteryHint(os: string, ignoring: boolean | null): boolean {
  return os === 'android' && ignoring === false;
}

export type ProblemKind = 'stuck' | 'offline' | 'signed_out' | 'error' | null;

export function problemKind(sync: SyncState): ProblemKind {
  if (sync.stuck) {
    return 'stuck';
  }
  switch (sync.last?.outcome) {
    case 'offline':
      return 'offline';
    case 'signed_out':
      return 'signed_out';
    case 'error':
      return 'error';
    default:
      return null;
  }
}

export function problemText(kind: NonNullable<ProblemKind>, sync: SyncState) {
  switch (kind) {
    case 'stuck':
      return sync.stuck?.kind === 'device-unknown'
        ? 'This phone is not registered to your account, so uploads are paused. Your segments are kept. Sign out and back in, or update the app.'
        : 'The server refused an upload and the app cannot fix it by retrying. Your segments are kept. Update the app.';
    case 'offline':
      return 'No connection to the server. Segments upload on their own when it is back.';
    case 'signed_out':
      return 'You are signed out, so nothing uploads.';
    case 'error':
      return 'The last upload did not finish. Segments are kept and will be tried again.';
  }
}

export function lastSyncText(sync: SyncState): string {
  const last = sync.last;
  if (!last) {
    return 'Not yet since the app opened';
  }
  const at = new Date(last.at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
  switch (last.outcome) {
    case 'synced':
      return `${at}, ${last.synced} uploaded${
        last.rejected ? `, ${last.rejected} rejected` : ''
      }`;
    case 'idle':
      return `${at}, nothing to upload`;
    case 'waiting':
      return `${at}, server asked to wait`;
    case 'offline':
      return `${at}, no connection`;
    case 'signed_out':
      return `${at}, signed out`;
    case 'stuck':
      return `${at}, stopped`;
    default:
      return `${at}, failed`;
  }
}

export function timeText(ms: number | null): string {
  return ms === null
    ? 'No segment yet'
    : new Date(ms).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      });
}
