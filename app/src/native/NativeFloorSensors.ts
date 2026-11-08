import type { CodegenTypes, TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export type LoggingStatus = {
  logging: boolean;
  label: string;
};

// has_barometer is snake_case to match the trace file format (T4).
export type FloorSensorsStatus = {
  logging: boolean;
  label: string;
  has_barometer: boolean;
  buffered: number;
  // Live detection (W3-1, W3-3, W3-7); the seam returns false, null and 0.
  detecting: boolean;
  last_segment_ms: number | null;
  rejected_count: number;
  no_checkin_count: number;
  longest_gap_s: number;
  gaps_over_threshold: number;
};

// Exactly the fields of the contract's Segment, which allows no others.
export type PendingSegment = {
  id: string;
  checkin_id: string;
  started_at: string; // ISO 8601 UTC
  building_id: number;
  ascent_m: number;
  duration_s: number;
  vert_speed_mps: number;
  steps: number;
  stair_prob: number;
  classifier_version: string;
};
export type ActiveCheckin = {
  checkin_id: string;
  building_id: number;
  building_name: string | null;
  valid_until_ms: number;
};
export type PendingChanged = { pending: number };

export interface Spec extends TurboModule {
  startLogging(label: string): void;
  stopLogging(): void;
  getStatus(): Promise<FloorSensorsStatus>;
  // Writes the last stopped session to files/traces as CSV; resolves to the file path.
  saveTrace(placement: string): Promise<string>;
  readonly onStatusChange: CodegenTypes.EventEmitter<LoggingStatus>;
  setActiveCheckin(
    checkinId: string,
    buildingId: number,
    buildingName: string | null,
    validUntilMs: number,
  ): void; // w3-engine
  clearActiveCheckin(): void; // w3-engine
  getActiveCheckin(): Promise<ActiveCheckin | null>; // w3-engine
  readonly onPendingChanged: CodegenTypes.EventEmitter<PendingChanged>; // w3-engine
  getPending(limit: number): Promise<PendingSegment[]>; // oldest first, status = pending; w3-outbox
  markSynced(ids: string[]): Promise<void>; // w3-outbox
  markRejected(ids: string[], reason: string): Promise<void>; // w3-outbox
  getPendingCount(): Promise<number>; // w3-outbox
  clearPending(): Promise<void>; // w3-outbox
  isIgnoringBatteryOptimizations(): Promise<boolean>; // w3-sync
  openBatteryOptimizationSettings(): void; // w3-sync
}

export default TurboModuleRegistry.getEnforcing<Spec>('FloorSensors');
