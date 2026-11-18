import { useEffect, useRef, useState } from 'react';
import type { components } from '../api/schema';
import { FloorSensors } from '../native/floorSensors';
import { currentRealtimeStatus } from './realtime';

export type WsEvent = components['schemas']['WsEvent'];
export type RealtimeStatus = 'connecting' | 'open' | 'closed' | 'auth_needed';

// Game events from the one native socket (and the poll), each event_id once.
export function useGameEvents(onEvent: (e: WsEvent) => void): {
  status: RealtimeStatus;
} {
  const [status, setStatus] = useState<RealtimeStatus>(currentRealtimeStatus);
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const eventSub = FloorSensors.onGameEvent(({ json }) => {
      let event: WsEvent;
      try {
        event = JSON.parse(json);
      } catch {
        return;
      }
      handler.current(event);
    });
    const stateSub = FloorSensors.onRealtimeState(({ state }) =>
      setStatus(state as RealtimeStatus),
    );
    return () => {
      eventSub.remove();
      stateSub.remove();
    };
  }, []);

  return { status };
}
