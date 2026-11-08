import { api, ApiError } from '../api/client';
import type { components } from '../api/schema';
import { getDeviceId } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';

type Flip = components['schemas']['BuildingFlip'];
type Result = components['schemas']['SegmentBatchResult'];

// The contract allows at most 100 segments per batch.
export const BATCH_SIZE = 100;
// Full-jitter backoff: wait random(0, min(cap, base * 2^attempt)). Five tries is about 30 s worst
// case, short enough for a background task.
export const BACKOFF_BASE_MS = 2_000;
export const BACKOFF_CAP_MS = 60_000;
export const MAX_ATTEMPTS = 5;

export type SyncOutcome =
  | 'synced' // the outbox is drained
  | 'idle' // nothing pending
  | 'offline' // network, 5xx or timeout after all attempts; rows stay pending
  | 'waiting' // the server asked us to wait (Retry-After)
  | 'signed_out'
  | 'stuck' // see SyncState.stuck
  | 'error'; // the outbox failed or the server answered nothing usable

export type SyncState = {
  running: boolean;
  last: {
    at: number;
    outcome: SyncOutcome;
    synced: number;
    rejected: number;
  } | null;
  // A batch the app cannot fix by retrying (422, 403). Rows stay pending until the app restarts.
  stuck: {
    kind: 'validation' | 'device-unknown' | 'forbidden';
    type: string;
  } | null;
  notBeforeMs: number | null;
};

const initial: SyncState = {
  running: false,
  last: null,
  stuck: null,
  notBeforeMs: null,
};
let state = initial;
const listeners = new Set<() => void>();
let flipHandler: ((flips: Flip[]) => void) | undefined;
let inFlight: Promise<SyncState> | null = null;

// Replaceable so tests run without waiting and with a fixed random source.
export const deps = {
  now: () => Date.now(),
  random: () => Math.random(),
  sleep: (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)),
};

export const getSyncState = () => state;
export function subscribeSync(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
// Week 4 hooks the flip banner here.
export function setFlipHandler(fn: ((flips: Flip[]) => void) | undefined) {
  flipHandler = fn;
}
export function resetSyncForTests() {
  state = initial;
  inFlight = null;
  flipHandler = undefined;
}
function setState(patch: Partial<SyncState>) {
  state = { ...state, ...patch };
  listeners.forEach(fn => fn());
}

/* eslint-disable no-bitwise -- the hash needs 32-bit integer maths */
// cyrb53, a 53-bit string hash. The key must stay under 255 characters, which 100 UUIDs exceed.
function hash(text: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 =
    Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^
    Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 =
    Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^
    Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16);
}

// The same ids give the same key, so a retry replays; a different set of ids is a new batch.
export function idempotencyKey(ids: string[]): string {
  return `seg-${ids.length}-${hash([...ids].sort().join(','))}`;
}

function stuckFrom(e: ApiError): NonNullable<SyncState['stuck']> {
  const type = String(
    (e.problem as { type?: unknown } | undefined)?.type ?? 'about:blank',
  );
  if (e.status === 403) {
    return {
      kind: type.includes('device-unknown') ? 'device-unknown' : 'forbidden',
      type,
    };
  }
  return { kind: 'validation', type };
}

async function run(): Promise<SyncState> {
  let synced = 0;
  let rejected = 0;
  const finish = (outcome: SyncOutcome) => {
    // A run with nothing to upload keeps the last real result on show (it is only the follow-up
    // to markSynced and onPendingChanged).
    const keep =
      outcome === 'idle' && state.last && state.last.outcome !== 'idle';
    setState({
      running: false,
      ...(keep ? {} : { last: { at: deps.now(), outcome, synced, rejected } }),
    });
    return state;
  };
  setState({ running: true });
  try {
    for (;;) {
      const pending = await FloorSensors.getPending(BATCH_SIZE);
      if (pending.length === 0) {
        return finish(synced + rejected > 0 ? 'synced' : 'idle');
      }
      const ids = pending.map(s => s.id);
      const body = { device_id: await getDeviceId(), segments: pending };
      const key = idempotencyKey(ids);

      let result: Result | undefined;
      for (let attempt = 0; !result; attempt++) {
        try {
          result = await api('post', '/segments', {
            header: { 'Idempotency-Key': key },
            body,
          });
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            return finish('signed_out'); // the client already tried the refresh
          }
          if (e instanceof ApiError && e.status !== 429 && e.status < 500) {
            // 403, 422 and any other 4xx: a retry cannot fix it, the app has a bug.
            const stuck = stuckFrom(e);
            // Only the problem type is logged, never the body.
            console.warn(`sync stopped: ${stuck.kind} (${stuck.type})`);
            setState({ stuck });
            return finish('stuck');
          }
          // 429, 5xx, network error or timeout.
          const retryAfterS = e instanceof ApiError ? e.retryAfterS : undefined;
          if (retryAfterS !== undefined) {
            setState({ notBeforeMs: deps.now() + retryAfterS * 1000 });
            return finish('waiting');
          }
          if (attempt + 1 >= MAX_ATTEMPTS) {
            return finish('offline');
          }
          await deps.sleep(
            deps.random() *
              Math.min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * 2 ** attempt),
          );
        }
      }

      const sent = new Set(ids);
      const accepted = result.accepted
        .map(a => a.id)
        .filter(id => sent.has(id));
      // Store the server's reason string as it is: the enum grows (overlap is coming).
      const byReason = new Map<string, string[]>();
      for (const r of result.rejected.filter(x => sent.has(x.id))) {
        byReason.set(r.reason, [...(byReason.get(r.reason) ?? []), r.id]);
      }
      // A failure below leaves the rows pending; the retry reuses the key and the server replays.
      if (accepted.length > 0) {
        await FloorSensors.markSynced(accepted);
        synced += accepted.length;
      }
      let batchRejected = 0;
      for (const [reason, reasonIds] of byReason) {
        await FloorSensors.markRejected(reasonIds, reason);
        batchRejected += reasonIds.length;
      }
      rejected += batchRejected;
      if (result.flips.length > 0) {
        flipHandler?.(result.flips);
      }
      // The server answered for none of them: stop, or the loop would send them forever.
      if (accepted.length + batchRejected === 0) {
        return finish('error');
      }
    }
  } catch {
    return finish('error');
  }
}

// One sync at a time: a trigger while one runs gets the running one.
export function syncNow(): Promise<SyncState> {
  if (inFlight) {
    return inFlight;
  }
  if (
    state.stuck ||
    (state.notBeforeMs !== null && deps.now() < state.notBeforeMs)
  ) {
    return Promise.resolve(state);
  }
  inFlight = run().finally(() => {
    inFlight = null;
  });
  return inFlight;
}
