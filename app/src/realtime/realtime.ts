import { AppState } from 'react-native';
import { api, WS_URL } from '../api/client';
import { getAccessToken, hasSession } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';
import type { RealtimeStatus } from './useGameEvents';

// Plan 7.2.1 fallback poll: at most this many pages of 100 events per sync run.
export const MAX_EVENT_PAGES = 5;

// The latest socket state, so a screen that mounts later starts from it.
let status: RealtimeStatus = 'closed';

export function currentRealtimeStatus(): RealtimeStatus {
  return status;
}

// Native never refreshes: it gets every access token from here (and from the refresh in client.ts).
export async function handOverToken(): Promise<void> {
  FloorSensors.configureRealtime(WS_URL, await getAccessToken());
}

// The notifier needs the player's team code and the building names, and runs without JS.
export async function loadRealtimeContext(): Promise<void> {
  const [stats, teams, buildings] = await Promise.all([
    api('get', '/me/season-stats'),
    api('get', '/teams'),
    api('get', '/buildings'),
  ]);
  const code = teams.find(t => t.id === stats.team_id)?.code ?? null;
  FloorSensors.setRealtimeContext(
    code,
    JSON.stringify(buildings.map(({ id, name }) => ({ id, name }))),
  );
}

// Signed in: hold the socket while the app is in the foreground. Returns the stop function.
export function startRealtimeLink(): () => void {
  const stateSub = FloorSensors.onRealtimeState(({ state }) => {
    status = state as RealtimeStatus;
  });
  const onForeground = () => {
    handOverToken().catch(() => {});
    FloorSensors.startRealtime();
  };
  const appSub = AppState.addEventListener('change', next => {
    if (next === 'active') {
      onForeground();
    } else {
      FloorSensors.stopRealtime();
    }
  });
  if (AppState.currentState === 'active') {
    onForeground();
  }
  // Offline at start: the notifier keeps the context stored from the last run. No session (the dev
  // sign-in skip): nothing to load.
  hasSession()
    .then(signedIn => (signedIn ? loadRealtimeContext() : undefined))
    .catch(() => {});
  return () => {
    appSub.remove();
    stateSub.remove();
    FloorSensors.stopRealtime();
  };
}

// GET /me/events from the last handled id, through the same native pipeline as the socket.
export async function pollGameEvents(): Promise<void> {
  let since = await FloorSensors.getLastEventId();
  for (let page = 0; page < MAX_EVENT_PAGES; page++) {
    const events = await api('get', '/me/events', {
      query: { since, limit: 100 },
    });
    FloorSensors.deliverPolledEvents(JSON.stringify(events));
    if (!events.has_more) {
      return;
    }
    since = events.last_event_id;
  }
}
