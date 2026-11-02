import type { ComponentType } from 'react';

export type Position = { latitude: number; longitude: number };

// Thrown by an adapter. 'denied': the user refused the permission. 'unavailable': no fix, no camera, or no library.
export class DeviceError extends Error {
  constructor(readonly kind: 'denied' | 'unavailable') {
    super(kind);
  }
}

// What the check-in screen needs from native libraries. Cristea picks the libraries (see PR notes);
// each is wrapped in one adapter that satisfies this interface.
export interface CheckinDeps {
  // Shows the camera and calls onScan with the raw text of each code it reads.
  ScannerView: ComponentType<{ onScan: (raw: string) => void }>;
  // Asks for camera permission; true when granted.
  requestCameraPermission(): Promise<boolean>;
  // Asks for location permission, then returns one fix. Throws DeviceError.
  getPosition(): Promise<Position>;
}

// Stand-in until the libraries are chosen: every device call reports 'unavailable'.
export const noDeviceLibs: CheckinDeps = {
  ScannerView: () => null,
  requestCameraPermission: async () => {
    throw new DeviceError('unavailable');
  },
  getPosition: async () => {
    throw new DeviceError('unavailable');
  },
};
