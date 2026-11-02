import type { ComponentType } from 'react';

export type Position = { latitude: number; longitude: number };

// Thrown by an adapter. 'denied': the user refused the permission. 'unavailable': no fix, no camera, or no library.
export class DeviceError extends Error {
  constructor(readonly kind: 'denied' | 'unavailable') {
    super(kind);
  }
}

// What the check-in screen needs from native libraries; deviceLibs.tsx is the real adapter, tests inject fakes.
export interface CheckinDeps {
  // Shows the camera and calls onScan with the raw text of each code it reads.
  ScannerView: ComponentType<{ onScan: (raw: string) => void }>;
  // Asks for camera permission; true when granted.
  requestCameraPermission(): Promise<boolean>;
  // Asks for location permission, then returns one fix. Throws DeviceError.
  getPosition(): Promise<Position>;
}
