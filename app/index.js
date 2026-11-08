/**
 * @format
 */

import { AppRegistry } from 'react-native';
import App from './App';
import { backgroundSyncTask } from './src/sync/triggers';
import { name as appName } from './app.json';

AppRegistry.registerComponent(appName, () => App);

// Started by the Kotlin WorkManager job (SyncTaskService).
AppRegistry.registerHeadlessTask('FloorWarsSync', () => backgroundSyncTask);
