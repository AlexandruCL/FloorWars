import type { components } from '../api/schema';

export type WsEvent = components['schemas']['WsEvent'];
export type RealtimeStatus = 'connecting' | 'open' | 'closed' | 'auth_needed';

// Seam: w4-realtime replaces the body; the signature is fixed.
export function useGameEvents(_onEvent: (e: WsEvent) => void): {
  status: RealtimeStatus;
} {
  return { status: 'closed' };
}
