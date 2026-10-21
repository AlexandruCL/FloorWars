import { fireEvent, render, screen } from '@testing-library/react-native';
import * as Keychain from 'react-native-keychain';
import App from '../App';
import { RootNavigator } from '../src/navigation/RootNavigator';

test('App starts on the Auth stack', async () => {
  await render(<App />);
  expect(screen.getAllByText('Sign in').length).toBeGreaterThan(0);
  expect(screen.queryByText('Home')).toBeNull();
});

test('signed-in users get the Main stack', async () => {
  await render(<RootNavigator isSignedIn />);
  expect(screen.getAllByText('Home').length).toBeGreaterThan(0);
  expect(screen.queryByText('Sign in')).toBeNull();
});

test('dev skip sign-in opens the Main stack', async () => {
  await render(<App />);
  await fireEvent.press(screen.getByText('Skip sign-in (dev)'));
  expect(screen.getAllByText('Home').length).toBeGreaterThan(0);
});

test('stub sign-in stores the dummy token and opens the Main stack', async () => {
  await render(<App />);
  await fireEvent.press(screen.getByText('Sign in (stub)'));
  expect(await screen.findAllByText('Home')).not.toHaveLength(0);
  expect(Keychain.setGenericPassword).toHaveBeenCalledWith(
    'stub',
    'stub-access-token',
    { service: 'floorwars.auth' },
  );
});
