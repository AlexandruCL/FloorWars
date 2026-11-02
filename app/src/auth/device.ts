import { Platform } from 'react-native';
import { FloorSensors } from '../native/floorSensors';
import type { components } from '../api/schema';
import { getDeviceId } from './session';

// Only what the contract's DeviceInfo asks for: install id, model, barometer flag.
export async function getDeviceInfo(): Promise<
  components['schemas']['DeviceInfo']
> {
  const c = Platform.constants as { Brand?: string; Model?: string };
  const has_barometer = await FloorSensors.getStatus()
    .then(s => s.has_barometer)
    .catch(() => false);
  return {
    id: await getDeviceId(),
    model: `${c.Brand ?? ''} ${c.Model ?? 'unknown'}`.trim().slice(0, 100),
    has_barometer,
  };
}
