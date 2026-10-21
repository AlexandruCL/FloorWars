import type { CodegenTypes, TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export type LoggingStatus = {
  logging: boolean;
  label: string;
};

export interface Spec extends TurboModule {
  startLogging(label: string): void;
  stopLogging(): void;
  readonly onStatusChange: CodegenTypes.EventEmitter<LoggingStatus>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('FloorSensors');
