import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import * as Keychain from 'react-native-keychain';
import { api, ApiError } from '../src/api/client';
import { getAccessToken, hasChosenTeam } from '../src/auth/session';
import { EmailScreen, OtpScreen, TeamScreen } from '../src/screens/AuthScreens';

jest.mock('../src/api/client', () => {
  const actual = jest.requireActual('../src/api/client');
  return { ...actual, api: jest.fn() };
});
const apiMock = api as unknown as jest.Mock;

const offline = () => new TypeError('Network request failed');
const navigation = { navigate: jest.fn(), replace: jest.fn() };

beforeEach(async () => {
  jest.clearAllMocks();
  await Keychain.resetGenericPassword({ service: 'floorwars.auth' });
  await Keychain.resetGenericPassword({ service: 'floorwars.team' });
});

async function fillEmail(value: string, confirm = true) {
  const props: any = { navigation, route: {} };
  await render(<EmailScreen {...props} />);
  await fireEvent.changeText(screen.getByLabelText('University e-mail'), value);
  if (confirm) {
    await fireEvent(
      screen.getByLabelText('I am 18 or older'),
      'valueChange',
      true,
    );
    await fireEvent(
      screen.getByLabelText('I accept the terms and privacy notice'),
      'valueChange',
      true,
    );
  }
  await fireEvent.press(screen.getByText('Send code'));
}

describe('EmailScreen', () => {
  test('rejects a malformed address without calling the server', async () => {
    await fillEmail('nope');
    expect(screen.getByText(/Enter a valid e-mail/)).toBeTruthy();
    expect(apiMock).not.toHaveBeenCalled();
  });

  test('needs the age and terms confirmations', async () => {
    await fillEmail('a@student.ro', false);
    expect(screen.getByText(/18 or older and accept the terms/)).toBeTruthy();
    expect(apiMock).not.toHaveBeenCalled();
  });

  test('sends only the e-mail, then opens the code screen', async () => {
    apiMock.mockResolvedValue(undefined);
    await fillEmail(' A@Student.ro ');
    await waitFor(() =>
      expect(navigation.navigate).toHaveBeenCalledWith('Otp', {
        email: 'a@student.ro',
      }),
    );
    expect(apiMock).toHaveBeenCalledWith('post', '/auth/otp', {
      body: { email: 'a@student.ro' },
    });
  });

  test('shows the offline message and stays usable', async () => {
    apiMock.mockRejectedValue(offline());
    await fillEmail('a@student.ro');
    expect(
      await screen.findByText("No connection. Try again when you're online."),
    ).toBeTruthy();
    expect(screen.getByText('Send code')).toBeTruthy();
  });

  test('an address off the allow-list gets a clear next step', async () => {
    apiMock.mockRejectedValue(new ApiError(403, {}));
    await fillEmail('a@gmail.com');
    expect(await screen.findByText(/Use your university e-mail/)).toBeTruthy();
  });
});

describe('OtpScreen', () => {
  const otp = () => {
    const props: any = {
      navigation,
      route: { params: { email: 'a@student.ro' } },
    };
    return render(<OtpScreen {...props} />);
  };

  test('keeps only digits and refuses a short code', async () => {
    await otp();
    const input = screen.getByLabelText('6-digit code');
    await fireEvent.changeText(input, '12a3');
    expect(input.props.value).toBe('123');
    await fireEvent.press(screen.getByText('Verify'));
    expect(
      screen.getByText('Enter the 6 digits from the e-mail.'),
    ).toBeTruthy();
    expect(apiMock).not.toHaveBeenCalled();
  });

  test('a wrong code says what to do next', async () => {
    apiMock.mockRejectedValue(new ApiError(401, {}));
    await otp();
    await fireEvent.changeText(screen.getByLabelText('6-digit code'), '123456');
    await fireEvent.press(screen.getByText('Verify'));
    expect(
      await screen.findByText(/Check the code and try again/),
    ).toBeTruthy();
  });

  test('a good code stores the tokens and moves to team choice', async () => {
    apiMock.mockResolvedValue({
      access_token: 'a',
      refresh_token: 'r',
      token_type: 'Bearer',
      expires_in: 900,
    });
    await otp();
    await fireEvent.changeText(screen.getByLabelText('6-digit code'), '123456');
    await fireEvent.press(screen.getByText('Verify'));
    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith('Team'),
    );
    expect(await getAccessToken()).toBe('a');
    const body = apiMock.mock.calls[0][2].body;
    expect(Object.keys(body).sort()).toEqual([
      'accept_terms',
      'code',
      'confirm_adult',
      'device',
      'email',
    ]);
    expect(Object.keys(body.device).sort()).toEqual([
      'has_barometer',
      'id',
      'model',
    ]);
  });
});

describe('TeamScreen', () => {
  const teams = [
    { id: 1, code: 'AC', color_hex: '#112233' },
    { id: 2, code: 'MEC', color_hex: '#445566' },
  ];
  const loaded = (t = teams) =>
    apiMock.mockImplementation(async (_m: string, path: string) =>
      path === '/teams' ? t : { id: 7, starts_at: '', ends_at: '' },
    );

  test('shows a loading state first', async () => {
    apiMock.mockReturnValue(new Promise(() => {}));
    await render(<TeamScreen onDone={jest.fn()} />);
    expect(screen.getByLabelText('Loading teams')).toBeTruthy();
  });

  test('error state offers a retry that recovers', async () => {
    apiMock.mockRejectedValue(offline());
    await render(<TeamScreen onDone={jest.fn()} />);
    expect(await screen.findByText(/No connection/)).toBeTruthy();
    loaded();
    await fireEvent.press(screen.getByText('Try again'));
    expect(await screen.findByText('AC')).toBeTruthy();
  });

  test('no active season is explained', async () => {
    apiMock.mockRejectedValue(new ApiError(404, {}));
    await render(<TeamScreen onDone={jest.fn()} />);
    expect(await screen.findByText(/No season is running/)).toBeTruthy();
  });

  test('empty state when the server has no teams', async () => {
    loaded([]);
    await render(<TeamScreen onDone={jest.fn()} />);
    expect(await screen.findByText(/No teams are set up yet/)).toBeTruthy();
  });

  test('joining posts the chosen team to the active season', async () => {
    loaded();
    const onDone = jest.fn();
    await render(<TeamScreen onDone={onDone} />);
    await fireEvent.press(await screen.findByText('MEC'));
    await fireEvent.press(screen.getByText('Join team'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(apiMock).toHaveBeenCalledWith('post', '/seasons/{id}/join', {
      path: { id: 7 },
      body: { team_id: 2 },
    });
    expect(await hasChosenTeam()).toBe(true);
  });

  test('a 409 means the team is already chosen and moves on', async () => {
    apiMock.mockImplementation(async (_m: string, path: string) => {
      if (path === '/teams') {
        return teams;
      }
      if (path === '/seasons/active') {
        return { id: 7 };
      }
      throw new ApiError(409, {});
    });
    const onDone = jest.fn();
    await render(<TeamScreen onDone={onDone} />);
    await fireEvent.press(await screen.findByText('AC'));
    await fireEvent.press(screen.getByText('Join team'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});

describe('stale validation errors', () => {
  test('consent error clears when a switch changes, not on the next submit', async () => {
    await fillEmail('a@student.ro', false);
    expect(screen.getByText(/18 or older and accept the terms/)).toBeTruthy();
    await fireEvent(
      screen.getByLabelText('I am 18 or older'),
      'valueChange',
      true,
    );
    expect(screen.queryByText(/18 or older and accept the terms/)).toBeNull();
  });

  test('e-mail error clears when the e-mail is edited', async () => {
    await fillEmail('nope');
    await fireEvent.changeText(
      screen.getByLabelText('University e-mail'),
      'a@student.ro',
    );
    expect(screen.queryByText(/Enter a valid e-mail/)).toBeNull();
  });

  test('code error clears when the code is edited', async () => {
    const props: any = { navigation, route: { params: { email: 'a@b.ro' } } };
    await render(<OtpScreen {...props} />);
    await fireEvent.press(screen.getByText('Verify'));
    expect(screen.getByText(/Enter the 6 digits/)).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('6-digit code'), '1');
    expect(screen.queryByText(/Enter the 6 digits/)).toBeNull();
  });
});
