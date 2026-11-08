import { Alert } from 'react-native';
import { fireEvent, render, screen } from '@testing-library/react-native';
import App from '../App';
import * as Keychain from 'react-native-keychain';
import { endSession, saveTokens } from '../src/auth/session';
import { FloorSensors } from '../src/native/floorSensors';

const sensors = FloorSensors as jest.Mocked<typeof FloorSensors>;

const realFetch = globalThis.fetch;

afterEach(() => {
  jest.restoreAllMocks();
  sensors.getPendingCount.mockResolvedValue(0);
  globalThis.fetch = realFetch;
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

async function signOutWithTokens(fetchImpl: jest.Mock) {
  const alert = await openConfirm(0);
  await saveTokens({ access_token: 'a', refresh_token: 'r1' } as never);
  globalThis.fetch = fetchImpl as never;
  alert.mock.calls[0][2]!.find(b => b.text === 'Sign out')!.onPress?.();
  expect(await screen.findByText('Send code')).toBeTruthy();
}

test('sign out revokes the refresh token before clearing the session', async () => {
  const fetchMock = jest.fn(async () => ({
    ok: true,
    status: 204,
    text: async () => '',
  }));
  await signOutWithTokens(fetchMock);
  const [url, init] = fetchMock.mock.calls[0] as unknown as [
    string,
    RequestInit,
  ];
  expect(url).toMatch(/\/auth\/logout$/);
  expect(JSON.parse(init.body as string)).toEqual({ refresh_token: 'r1' });
  expect(fetchMock.mock.invocationCallOrder[0]).toBeLessThan(
    (Keychain.resetGenericPassword as jest.Mock).mock.invocationCallOrder.at(
      -1,
    )!,
  );
});

test('sign out still ends the session when the logout call fails', async () => {
  await signOutWithTokens(jest.fn().mockRejectedValue(new Error('offline')));
  expect(await Keychain.getGenericPassword({ service: 'floorwars.auth' })).toBe(
    false,
  );
});
