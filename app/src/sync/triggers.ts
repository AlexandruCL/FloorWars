import { AppState } from 'react-native';
import { FloorSensors } from '../native/floorSensors';
import { resetSync, syncNow } from './syncWorker';

export const DEBOUNCE_MS = 3_000;

// Foreground and new-segment triggers. The 15-minute background run comes from the Kotlin
// WorkManager job through the headless task in index.js. Returns the stop function.
export function startSyncTriggers(): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const pendingSub = FloorSensors.onPendingChanged(() => {
    clearTimeout(timer);
    timer = setTimeout(() => syncNow(), DEBOUNCE_MS);
  });
  const appSub = AppState.addEventListener('change', status => {
    if (status === 'active') {
      syncNow();
    }
  });
  syncNow();
  return () => {
    clearTimeout(timer);
    pendingSub.remove();
    appSub.remove();
    resetSync();
  };
}

// Registered in index.js as a headless task; the WorkManager job starts it.
export async function backgroundSyncTask(): Promise<void> {
  await syncNow();
}
