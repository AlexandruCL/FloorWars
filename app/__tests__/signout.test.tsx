import { Alert } from 'react-native';
import { fireEvent, render, screen } from '@testing-library/react-native';
import App from '../App';
import { endSession } from '../src/auth/session';
import { FloorSensors } from '../src/native/floorSensors';

const sensors = FloorSensors as jest.Mocked<typeof FloorSensors>;

afterEach(() => {
  jest.restoreAllMocks();
  sensors.getPendingCount.mockResolvedValue(0);
});

async function openConfirm(pending: number) {
  sensors.getPendingCount.mockResolvedValue(pending);
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  await render(<App />);
  await fireEvent.press(await screen.findByText('Skip sign-in (dev)'));
  await fireEvent.press((await screen.findAllByText('Sign out'))[0]);
  await screen.findByText('Status');
  return alert;
}

test('confirm shows the pending count and the deletion warning', async () => {
  const alert = await openConfirm(3);
  await jest.requireActual('react').act(async () => {});
  expect(alert).toHaveBeenCalledTimes(1);
  expect(alert.mock.calls[0][1]).toBe(
    '3 segments are not uploaded yet and will be deleted.',
  );
});

test('cancel does nothing', async () => {
  const alert = await openConfirm(1);
  const buttons = alert.mock.calls[0][2]!;
  buttons.find(b => b.text === 'Cancel')!.onPress?.();
  expect(sensors.clearPending).not.toHaveBeenCalled();
  expect(screen.queryByText('Send code')).toBeNull();
});

test('confirm ends the session and returns to the e-mail screen', async () => {
  const alert = await openConfirm(0);
  const buttons = alert.mock.calls[0][2]!;
  buttons.find(b => b.text === 'Sign out')!.onPress?.();
  expect(await screen.findByText('Send code')).toBeTruthy();
  expect(sensors.clearPending).toHaveBeenCalled();
});

test('endSession clears pending and the active check-in', async () => {
  await endSession();
  expect(sensors.clearPending).toHaveBeenCalled();
  expect(sensors.clearActiveCheckin).toHaveBeenCalled();
});

test('endSession still finishes when a native clear fails', async () => {
  const ended = jest.fn();
  const { setOnSessionEnded } = require('../src/auth/session');
  setOnSessionEnded(ended);
  sensors.clearPending.mockRejectedValueOnce(new Error('db'));
  sensors.clearActiveCheckin.mockImplementationOnce(() => {
    throw new Error('svc');
  });
  await endSession();
  expect(sensors.clearActiveCheckin).toHaveBeenCalled();
  expect(ended).toHaveBeenCalled();
  setOnSessionEnded(undefined);
});
