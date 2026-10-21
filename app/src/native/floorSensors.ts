import { PermissionsAndroid, Platform } from 'react-native';
import type { Permission, PermissionStatus } from 'react-native';

export { default as FloorSensors } from './NativeFloorSensors';

// Missing from PermissionsAndroid.PERMISSIONS. Install-time, so check only.
const FOREGROUND_SERVICE_HEALTH =
  'android.permission.FOREGROUND_SERVICE_HEALTH' as Permission;

// Runtime permissions and the API level where each starts needing a prompt.
const RUNTIME: [Permission, number][] = [
  [PermissionsAndroid.PERMISSIONS.ACTIVITY_RECOGNITION, 29],
  [PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS, 33],
];

// Prompts for what this API level needs. Below a permission's API level it is reported as granted.
export async function requestPermissions(): Promise<
  Record<string, PermissionStatus>
> {
  const api = Platform.Version as number;
  const results: Record<string, PermissionStatus> = {};
  const toAsk: Permission[] = [];
  for (const [permission, since] of RUNTIME) {
    if (api >= since) {
      toAsk.push(permission);
    } else {
      results[permission] = 'granted';
    }
  }
  Object.assign(results, await PermissionsAndroid.requestMultiple(toAsk));
  const healthGranted =
    api < 34 || (await PermissionsAndroid.check(FOREGROUND_SERVICE_HEALTH));
  results[FOREGROUND_SERVICE_HEALTH] = healthGranted ? 'granted' : 'denied';
  return results;
}
