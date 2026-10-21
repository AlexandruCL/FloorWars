import { act, fireEvent, render, screen } from '@testing-library/react-native';
import Share from 'react-native-share';
import NativeFloorSensors from '../src/native/NativeFloorSensors';
import type { LoggingStatus } from '../src/native/NativeFloorSensors';
import { requestPermissions } from '../src/native/floorSensors';
import { SensorLoggerScreen } from '../src/screens/SensorLoggerScreen';

jest.mock('../src/native/floorSensors', () => ({
  ...jest.requireActual('../src/native/floorSensors'),
  requestPermissions: jest.fn(),
}));

const native = jest.mocked(NativeFloorSensors);
const permissions = jest.mocked(requestPermissions);
const ACTIVITY = 'android.permission.ACTIVITY_RECOGNITION';

function statusHandler() {
  return native.onStatusChange.mock.lastCall![0] as (
    event: LoggingStatus,
  ) => Promise<void>;
}

beforeEach(() => jest.clearAllMocks());

test('records with the picked label, saves with the placement and shares the CSV', async () => {
  permissions.mockResolvedValue({ [ACTIVITY]: 'granted' });
  await render(<SensorLoggerScreen />);
  await fireEvent.press(screen.getByText('stairs_down'));
  await fireEvent.press(screen.getByText('hand'));
  await fireEvent.press(screen.getByText('Start recording'));
  expect(native.startLogging).toHaveBeenCalledWith('stairs_down');

  await act(() => statusHandler()({ logging: true, label: 'stairs_down' }));
  expect(screen.getByText('00:00')).toBeTruthy();
  expect(screen.getByText('Recording stairs_down, hand')).toBeTruthy();

  await fireEvent.press(screen.getByText('Stop and save'));
  expect(native.stopLogging).toHaveBeenCalled();
  await act(() => statusHandler()({ logging: false, label: '' }));
  expect(native.saveTrace).toHaveBeenCalledWith('hand');

  await fireEvent.press(await screen.findByText('Share CSV'));
  expect(Share.open).toHaveBeenCalledWith({
    url: 'file:///data/files/traces/stairs_up_pocket.csv',
    type: 'text/csv',
    failOnCancel: false,
  });
});

test('does not start without the activity permission', async () => {
  permissions.mockResolvedValue({ [ACTIVITY]: 'denied' });
  await render(<SensorLoggerScreen />);
  await fireEvent.press(screen.getByText('Start recording'));
  expect(native.startLogging).not.toHaveBeenCalled();
  expect(
    screen.getByText(/Physical activity permission is needed/),
  ).toBeTruthy();
});
