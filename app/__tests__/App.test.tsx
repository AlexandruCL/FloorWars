import { fireEvent, render, screen } from '@testing-library/react-native';
import * as Keychain from 'react-native-keychain';
import App from '../App';
import { RootNavigator } from '../src/navigation/RootNavigator';

beforeEach(async () => {
  await Keychain.resetGenericPassword({ service: 'floorwars.auth' });
  await Keychain.resetGenericPassword({ service: 'floorwars.team' });
});

test('App starts on the Auth stack', async () => {
  await render(<App />);
  expect(await screen.findByText('Send code')).toBeTruthy();
  expect(screen.queryByText('Status')).toBeNull();
});

test('signed-in users get the Main stack', async () => {
  await render(<RootNavigator isSignedIn />);
  expect(screen.getAllByText('Status').length).toBeGreaterThan(0);
  expect(screen.queryByText('Send code')).toBeNull();
});

test('dev skip sign-in opens the Main stack', async () => {
  await render(<App />);
  await fireEvent.press(await screen.findByText('Skip sign-in (dev)'));
  expect(screen.getAllByText('Status').length).toBeGreaterThan(0);
});

test('stored tokens and a chosen team restore straight into Main', async () => {
  await Keychain.setGenericPassword('tokens', '{"access":"a","refresh":"r"}', {
    service: 'floorwars.auth',
  });
  await Keychain.setGenericPassword('team', '1', { service: 'floorwars.team' });
  await render(<App />);
  expect((await screen.findAllByText('Status')).length).toBeGreaterThan(0);
});
