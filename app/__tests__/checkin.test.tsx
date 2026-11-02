import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { Text } from 'react-native';
import { api, ApiError } from '../src/api/client';
import { DeviceError, type CheckinDeps } from '../src/checkin/deps';
import { parseQrPayload } from '../src/checkin/qr';
import {
  errorKind,
  errorMessage,
  minutesLeft,
  successText,
  type ErrorKind,
} from '../src/checkin/state';
import { CheckinScreen } from '../src/screens/CheckinScreen';

jest.mock('../src/api/client', () => {
  const actual = jest.requireActual('../src/api/client');
  return { ...actual, api: jest.fn() };
});
const apiMock = api as unknown as jest.Mock;

// Node global in Jest; the app tsconfig has no node types.
declare const Buffer: { from(s: string): { toString(enc: string): string } };
const b64url = (o: object) =>
  Buffer.from(JSON.stringify(o)).toString('base64url');
const NOW = Date.UTC(2026, 10, 2, 12, 0, 0);
const token = (exp: number) =>
  `fwq1.${b64url({ b: 1, exp, kid: 'abcd1234', nbf: 0, v: 1 })}.c2ln`;
const problem = (slug: string) =>
  new ApiError(403, { type: `urn:floorwars:problem:${slug}`, status: 403 });

describe('parseQrPayload', () => {
  test('valid token is returned trimmed and not expired', () => {
    const t = token(NOW / 1000 + 60);
    expect(parseQrPayload(` ${t}\n`, NOW)).toEqual({
      ok: true,
      token: t,
      expired: false,
    });
  });
  test('expired-looking token is flagged', () => {
    expect(parseQrPayload(token(NOW / 1000 - 1), NOW)).toMatchObject({
      ok: true,
      expired: true,
    });
  });
  test.each([
    ['empty', ''],
    ['a URL', 'https://example.com/menu'],
    ['wrong prefix', token(1).replace('fwq1', 'fwq2')],
    ['two parts', 'fwq1.abc'],
    ['payload not JSON', 'fwq1.bm90anNvbg.c2ln'],
    ['no exp', `fwq1.${b64url({ v: 1 })}.c2ln`],
    ['too long', `fwq1.${'a'.repeat(600)}.c2ln`],
  ])('malformed: %s', (_, raw) => {
    expect(parseQrPayload(raw, NOW)).toEqual({ ok: false });
  });
});

describe('errorKind', () => {
  test.each([
    ['qr-expired', 'expired'],
    ['qr-not-yet-valid', 'expired'],
    ['qr-malformed', 'rejected'],
    ['qr-invalid', 'rejected'],
    ['building-unknown', 'rejected'],
    ['outside-geofence', 'outside'],
    ['location-inaccurate', 'outside'],
  ])('problem %s -> %s', (slug, kind) => {
    expect(errorKind(problem(slug), 'qr')).toBe(kind);
  });
  test('503 qr-unavailable -> unavailable', () => {
    const e = new ApiError(503, {
      type: 'urn:floorwars:problem:qr-unavailable',
    });
    expect(errorKind(e, 'qr')).toBe('unavailable');
  });
  test('ignores the detail text', () => {
    const e = new ApiError(403, {
      type: 'urn:floorwars:problem:qr-expired',
      detail: 'outside the geofence',
    });
    expect(errorKind(e, 'geofence')).toBe('expired');
  });
  test('untyped 403 falls back on the method', () => {
    expect(errorKind(new ApiError(403, {}), 'qr')).toBe('rejected');
    expect(errorKind(new ApiError(403, undefined), 'geofence')).toBe('outside');
  });
  test('device errors, network, 5xx, 429', () => {
    expect(errorKind(new DeviceError('denied'), 'qr')).toBe('denied');
    expect(errorKind(new DeviceError('unavailable'), 'geofence')).toBe(
      'unavailable',
    );
    expect(errorKind(new TypeError('Network request failed'), 'qr')).toBe(
      'failed',
    );
    expect(errorKind(new ApiError(500, undefined), 'qr')).toBe('failed');
    expect(errorKind(new ApiError(429, {}), 'geofence')).toBe('failed');
  });
});

describe('copy', () => {
  const kinds: ErrorKind[] = [
    'expired',
    'rejected',
    'outside',
    'denied',
    'unavailable',
    'failed',
  ];
  test.each(kinds)('%s names a next step for both methods', kind => {
    for (const m of ['qr', 'geofence'] as const) {
      expect(errorMessage(kind, m)).toMatch(
        /scan|location|try again|Settings/i,
      );
    }
  });
  test('denied names the permission that was refused', () => {
    expect(errorMessage('denied', 'qr')).toMatch(/Camera/);
    expect(errorMessage('denied', 'geofence')).toMatch(/Location/);
  });
  test('success text and minutes left', () => {
    const c = {
      id: 'x',
      building_id: 1,
      method: 'qr' as const,
      valid_from: new Date(NOW).toISOString(),
      valid_until: new Date(NOW + 90 * 60000).toISOString(),
    };
    expect(successText('Building X', c, NOW + 30000)).toBe(
      'Checked in: Building X, 90 min left',
    );
    expect(successText('Building X', c, NOW + 61000)).toBe(
      'Checked in: Building X, 89 min left',
    );
    expect(minutesLeft(c, NOW - 3600000)).toBe(90); // phone clock behind: capped
    expect(minutesLeft(c, NOW + 99 * 60000)).toBe(0);
  });
});

describe('CheckinScreen', () => {
  const nav: any = { goBack: jest.fn() };
  const created = () => ({
    id: 'u',
    building_id: 2,
    method: 'qr',
    valid_from: new Date().toISOString(),
    valid_until: new Date(Date.now() + 90 * 60000).toISOString(),
  });
  const goodCode = () => token(Date.now() / 1000 + 600);
  const deps = (over: Partial<CheckinDeps> = {}): CheckinDeps => ({
    ScannerView: ({ onScan }) => (
      <Text onPress={() => onScan(goodCode())}>fake-camera</Text>
    ),
    requestCameraPermission: async () => true,
    getPosition: async () => ({ latitude: 45.75, longitude: 21.23 }),
    ...over,
  });
  const open = (d: CheckinDeps) =>
    render(<CheckinScreen navigation={nav} route={{} as any} deps={d} />);
  beforeEach(() => apiMock.mockReset());

  test('asks for nothing until a button is tapped', async () => {
    const d = deps({ requestCameraPermission: jest.fn(async () => true) });
    await open(d);
    expect(d.requestCameraPermission).not.toHaveBeenCalled();
    expect(apiMock).not.toHaveBeenCalled();
  });

  test('scan to success sends the token and names the building', async () => {
    apiMock.mockImplementation(async (_m, path) =>
      path === '/checkins' ? created() : [{ id: 2, name: 'Building X' }],
    );
    await open(deps());
    await fireEvent.press(screen.getByText('Scan entrance code'));
    const cam = await screen.findByText('fake-camera');
    await fireEvent.press(cam);
    await fireEvent.press(cam); // a second frame with the same code is ignored
    expect(
      await screen.findByText(/Checked in: Building X, 90 min left/),
    ).toBeTruthy();
    const posts = apiMock.mock.calls.filter(c => c[1] === '/checkins');
    expect(posts).toHaveLength(1);
    expect(posts[0][2].body).toMatchObject({ method: 'qr' });
  });

  test('expired-looking code is not sent', async () => {
    await open(
      deps({
        ScannerView: ({ onScan }) => (
          <Text onPress={() => onScan(token(1))}>fake-camera</Text>
        ),
      }),
    );
    await fireEvent.press(screen.getByText('Scan entrance code'));
    await fireEvent.press(await screen.findByText('fake-camera'));
    expect(await screen.findByText(/has expired/)).toBeTruthy();
    expect(apiMock).not.toHaveBeenCalled();
  });

  test('camera permission denied', async () => {
    await open(deps({ requestCameraPermission: async () => false }));
    await fireEvent.press(screen.getByText('Scan entrance code'));
    expect(await screen.findByText(/Camera access is off/)).toBeTruthy();
    expect(screen.getByText('Open Settings')).toBeTruthy();
  });

  test('location path sends only the position; server 403 outside-geofence', async () => {
    apiMock.mockRejectedValue(problem('outside-geofence'));
    await open(deps());
    await fireEvent.press(screen.getByText('Use my location'));
    expect(await screen.findByText(/not close enough/)).toBeTruthy();
    expect(apiMock.mock.calls[0][2].body).toEqual({
      method: 'geofence',
      latitude: 45.75,
      longitude: 21.23,
    });
  });

  test('location permission denied', async () => {
    await open(
      deps({
        getPosition: async () => {
          throw new DeviceError('denied');
        },
      }),
    );
    await fireEvent.press(screen.getByText('Use my location'));
    await waitFor(() =>
      expect(screen.getByText(/Location access is off/)).toBeTruthy(),
    );
  });

  test('rejected token, then success even when the building name cannot be fetched', async () => {
    apiMock.mockRejectedValueOnce(problem('qr-invalid'));
    await open(deps());
    await fireEvent.press(screen.getByText('Scan entrance code'));
    await fireEvent.press(await screen.findByText('fake-camera'));
    expect(await screen.findByText(/was not accepted/)).toBeTruthy();

    apiMock.mockReset();
    apiMock.mockImplementation(async (_m, path) => {
      if (path === '/checkins') {
        return created();
      }
      throw new TypeError('offline');
    });
    await fireEvent.press(screen.getByText('Scan again'));
    await fireEvent.press(await screen.findByText('fake-camera'));
    expect(await screen.findByText(/Checked in: Building 2,/)).toBeTruthy();
  });
});
