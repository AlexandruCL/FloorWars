import { act, fireEvent, render, screen } from '@testing-library/react-native';
import NativeFloorSensors from '../src/native/NativeFloorSensors';
import type { LoggingStatus } from '../src/native/NativeFloorSensors';
import { FloorSensorsDebug } from '../src/native/FloorSensorsDebug';

const native = jest.mocked(NativeFloorSensors);

test('buttons call startLogging("test") and stopLogging()', async () => {
  await render(<FloorSensorsDebug />);
  await fireEvent.press(screen.getByText('startLogging("test")'));
  expect(native.startLogging).toHaveBeenCalledWith('test');
  await fireEvent.press(screen.getByText('stopLogging()'));
  expect(native.stopLogging).toHaveBeenCalled();
});

test('onStatusChange events update the status line', async () => {
  await render(<FloorSensorsDebug />);
  const handler = native.onStatusChange.mock.lastCall![0] as (
    event: LoggingStatus,
  ) => void;
  await act(() => handler({ logging: true, label: 'test' }));
  expect(screen.getByText('FloorSensors: logging "test"')).toBeTruthy();
});

test('getStatus() button shows the native status', async () => {
  await render(<FloorSensorsDebug />);
  await fireEvent.press(screen.getByText('getStatus()'));
  expect(native.getStatus).toHaveBeenCalled();
  expect(
    await screen.findByText(
      '{"logging":false,"label":"","has_barometer":true,"buffered":0}',
    ),
  ).toBeTruthy();
});
