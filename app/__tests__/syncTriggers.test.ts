import { ApiError } from '../src/api/client';
import { FloorSensors } from '../src/native/floorSensors';
import { getSyncState, resetSyncForTests } from '../src/sync/syncWorker';
import { startSyncTriggers } from '../src/sync/triggers';

jest.mock('../src/api/client', () => ({
  ...jest.requireActual('../src/api/client'),
  api: jest.fn(),
}));
const { api } = jest.requireMock('../src/api/client') as { api: jest.Mock };
const native = FloorSensors as unknown as Record<string, jest.Mock>;

beforeEach(() => {
  resetSyncForTests();
  api.mockReset();
  jest.spyOn(console, 'warn').mockImplementation(() => {});
});

test('stopping the triggers (a sign-out) clears a stuck sync state', async () => {
  native.getPending.mockResolvedValue([
    {
      id: '00000000-0000-4000-8000-000000000001',
      checkin_id: 'c1',
      started_at: '2026-11-08T10:00:00Z',
      building_id: 1,
      ascent_m: 3,
      duration_s: 20,
      vert_speed_mps: 0.15,
      steps: 20,
      stair_prob: 1,
      classifier_version: 'rules-1',
    },
  ]);
  api.mockRejectedValue(
    new ApiError(403, { type: 'urn:floorwars:problem:device-unknown' }),
  );
  const stop = startSyncTriggers();
  await jest.requireActual('react').act(async () => {});
  await new Promise<void>(resolve => setImmediate(() => resolve()));
  expect(getSyncState().stuck).not.toBeNull();
  stop();
  expect(getSyncState().stuck).toBeNull();
});
