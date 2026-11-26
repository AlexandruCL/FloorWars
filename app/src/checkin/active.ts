import { useCallback, useEffect, useState } from 'react';
import { PermissionsAndroid } from 'react-native';
import FloorSensors from '../native/NativeFloorSensors';
import {
  FloorSensors as FloorSensorsApi,
  requestPermissions,
} from '../native/floorSensors';
import type { ActiveCheckin } from '../native/NativeFloorSensors';
import type { Checkin } from './state';

// Hands the check-in to the native service, which stores it, attributes climbs to it and runs the
// sensors until it expires. Replaces any earlier one, as the server does. name: null when unknown.
// It is stored before any permission dialog, and the caller does not wait for the dialogs: a
// slow or cancelled prompt cannot lose the check-in or hold up the success screen. The service
// starts only once activity recognition is granted, so a grant sends the check-in again.
export async function setActiveCheckin(
  c: Checkin,
  buildingName: string | null,
): Promise<void> {
  const send = () =>
    FloorSensors.setActiveCheckin(
      c.id,
      c.building_id,
      buildingName,
      Date.parse(c.valid_until),
    );
  send();
  requestPermissions()
    .then(result => {
      if (
        result[PermissionsAndroid.PERMISSIONS.ACTIVITY_RECOGNITION] ===
        'granted'
      ) {
        send();
      }
    })
    .catch(() => {
      // A failed prompt keeps the stored check-in; detection starts at the next app start.
    });
}

// The active check-in, null when none or expired, read again whenever the screen comes into view.
export function useActiveCheckin(navigation: {
  addListener: (event: 'focus', fn: () => void) => () => void;
}): ActiveCheckin | null {
  const [checkin, setCheckin] = useState<ActiveCheckin | null>(null);
  const read = useCallback(() => {
    FloorSensorsApi.getActiveCheckin().then(
      c => setCheckin(c && c.valid_until_ms > Date.now() ? c : null),
      () => setCheckin(null),
    );
  }, []);
  useEffect(() => {
    read();
    return navigation.addListener('focus', read);
  }, [navigation, read]);
  return checkin;
}
