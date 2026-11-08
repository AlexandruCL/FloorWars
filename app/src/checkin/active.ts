import { PermissionsAndroid } from 'react-native';
import FloorSensors from '../native/NativeFloorSensors';
import { requestPermissions } from '../native/floorSensors';
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
