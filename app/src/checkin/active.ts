import FloorSensors from '../native/NativeFloorSensors';
import type { Checkin } from './state';

// Hands the check-in to the native service, which stores it, attributes climbs to it and runs the
// sensors until it expires. Replaces any earlier one, as the server does. name: null when unknown.
export function setActiveCheckin(
  c: Checkin,
  buildingName: string | null,
): void {
  FloorSensors.setActiveCheckin(
    c.id,
    c.building_id,
    buildingName,
    Date.parse(c.valid_until),
  );
}
