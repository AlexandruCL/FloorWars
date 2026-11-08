import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { AppState } from 'react-native';
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

// The Home screen heading is "Home" now and "Status" once the status screen lands.
const HOME = /^(Home|Status)$/;

describe('season check at start', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  async function startSignedIn(joined: string, active: number | 'offline') {
    await Keychain.setGenericPassword(
      'tokens',
      '{"access":"a","refresh":"r"}',
      { service: 'floorwars.auth' },
    );
    await Keychain.setGenericPassword('team', joined, {
      service: 'floorwars.team',
    });
    globalThis.fetch = jest.fn(async (url: string) => {
      if (active === 'offline') {
        throw new TypeError('Network request failed');
      }
      const body = url.endsWith('/teams')
        ? []
        : { id: active, starts_at: '', ends_at: '' };
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as never;
    await render(<App />);
  }

  test('a different active season shows the team picker again', async () => {
    await startSignedIn('1', 2);
    expect(await screen.findByText('Pick your team')).toBeTruthy();
    expect(screen.queryByText(HOME)).toBeNull();
  });

  test('the same active season goes straight in', async () => {
    await startSignedIn('2', 2);
    expect((await screen.findAllByText(HOME)).length).toBeGreaterThan(0);
  });

  test('the old team flag counts as season 1', async () => {
    await startSignedIn('1', 1);
    expect((await screen.findAllByText(HOME)).length).toBeGreaterThan(0);
  });

  test('an unreadable season keeps the user in', async () => {
    await startSignedIn('1', 'offline');
    expect((await screen.findAllByText(HOME)).length).toBeGreaterThan(0);
  });

  test('a season that rolls over while the app is open shows the picker on return', async () => {
    const handlers: ((status: string) => void)[] = [];
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((
      _type: string,
      fn: (status: string) => void,
    ) => {
      handlers.push(fn);
      return { remove: jest.fn() };
    }) as never);
    await startSignedIn('1', 1);
    expect((await screen.findAllByText(HOME)).length).toBeGreaterThan(0);
    // Season 2 is now the running one.
    globalThis.fetch = jest.fn(async (url: string) => ({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify(
          url.endsWith('/teams') ? [] : { id: 2, starts_at: '', ends_at: '' },
        ),
    })) as never;
    await act(async () => {
      handlers.forEach(fn => fn('active'));
    });
    expect(await screen.findByText('Pick your team')).toBeTruthy();
  });
});
