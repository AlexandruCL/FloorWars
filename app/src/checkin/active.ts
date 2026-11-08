import FloorSensors from '../native/NativeFloorSensors';
import { requestPermissions } from '../native/floorSensors';
import type { Checkin } from './state';

// Hands the check-in to the native service, which stores it, attributes climbs to it and runs the
// sensors until it expires. Replaces any earlier one, as the server does. name: null when unknown.
// Asks for the sensor permissions first: the service starts only once activity recognition is
// granted, so a grant here starts detection now. On denial the check-in is still stored.
export async function setActiveCheckin(
  c: Checkin,
  buildingName: string | null,
): Promise<void> {
  try {
    await requestPermissions();
  } catch {
    // A failed prompt must not lose the check-in; native stores it and skips detection.
  }
  FloorSensors.setActiveCheckin(
    c.id,
    c.building_id,
    buildingName,
    Date.parse(c.valid_until),
  );
}
