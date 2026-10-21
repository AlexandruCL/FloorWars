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
};

export interface Spec extends TurboModule {
  startLogging(label: string): void;
  stopLogging(): void;
  getStatus(): Promise<FloorSensorsStatus>;
  // Writes the last stopped session to files/traces as CSV; resolves to the file path.
  saveTrace(placement: string): Promise<string>;
  readonly onStatusChange: CodegenTypes.EventEmitter<LoggingStatus>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('FloorSensors');
