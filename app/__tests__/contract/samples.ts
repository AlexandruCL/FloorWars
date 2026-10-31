// Contract samples: typed requests and responses that must compile against the types generated
// from /contracts/openapi.yaml. Each @ts-expect-error marks input the contract must reject; if the
// contract stops rejecting it, the unused directive is itself a compile error.
// Checked by __tests__/apiContract.typecheck.test.js (and by tsc --noEmit).
import { api } from '../../src/api/client';
import type { components, paths } from '../../src/api/schema';

type Schemas = components['schemas'];
type JsonBody<P extends keyof paths, M extends 'get' | 'post'> = NonNullable<
  paths[P][M]
> extends { requestBody?: { content: { 'application/json': infer B } } }
  ? B
  : never;

// POST /auth/verify
export const verifyRequest: JsonBody<'/auth/verify', 'post'> = {
  email: 'student@example.edu',
  code: '123456',
  device: {
    id: '7c9e6679-7425-40de-944b-e07fc1f90ae7',
    model: 'samsung SM-S918B',
    has_barometer: true,
  },
  accept_terms: true,
  confirm_adult: true,
};
// @ts-expect-error device is required (0.4.0-draft)
export const verifyMissingDevice: Schemas['OtpVerifyRequest'] = {
  email: 'student@example.edu',
  code: '123456',
};

// GET /seasons/active
export const activeSeason: Schemas['Season'] = {
  id: 1,
  starts_at: '2026-11-02T00:00:00Z',
  ends_at: '2026-11-16T00:00:00Z',
};
export const verifyResponse: paths['/auth/verify']['post']['responses'][200]['content']['application/json'] =
  {
    access_token: 'a',
    refresh_token: 'r',
    token_type: 'Bearer',
    expires_in: 900,
  };
// @ts-expect-error code is required
export const verifyMissingCode: Schemas['OtpVerifyRequest'] = {
  email: 'student@example.edu',
};
export const wrongTokenType: Schemas['TokenPair'] = {
  access_token: 'a',
  refresh_token: 'r',
  // @ts-expect-error token_type is the literal Bearer
  token_type: 'Basic',
  expires_in: 900,
};

// POST /checkins
export const qrCheckin: JsonBody<'/checkins', 'post'> = {
  method: 'qr',
  qr_token: 'signed-token',
};
export const geofenceCheckin: JsonBody<'/checkins', 'post'> = {
  method: 'geofence',
  latitude: 44.43,
  longitude: 26.1,
};
export const mixedCheckin: JsonBody<'/checkins', 'post'> = {
  method: 'geofence',
  // @ts-expect-error a geofence check-in takes coordinates, not a QR token
  qr_token: 'signed-token',
};
export const checkinResponse: paths['/checkins']['post']['responses'][201]['content']['application/json'] =
  {
    id: '00000000-0000-4000-8000-000000000001',
    building_id: 1,
    method: 'qr',
    valid_from: '2026-11-02T10:00:00Z',
    valid_until: '2026-11-02T11:30:00Z',
  };

// POST /segments (the plan's example body, section 6)
export const segment: Schemas['Segment'] = {
  id: '00000000-0000-4000-8000-000000000002',
  checkin_id: '00000000-0000-4000-8000-000000000001',
  started_at: '2026-11-02T10:14:03Z',
  building_id: 4,
  ascent_m: 9.7,
  duration_s: 22,
  vert_speed_mps: 0.44,
  steps: 58,
  stair_prob: 0.93,
  classifier_version: 'rules-1',
};
export const batch: JsonBody<'/segments', 'post'> = { segments: [segment] };
export const segmentHeaders: paths['/segments']['post']['parameters']['header'] =
  { 'Idempotency-Key': 'batch-1' };
// @ts-expect-error Idempotency-Key is required
export const noIdempotencyKey: paths['/segments']['post']['parameters']['header'] =
  {};
export const batchResult: paths['/segments']['post']['responses'][200]['content']['application/json'] =
  {
    accepted: [{ id: segment.id, steps_scored: 58, points: 58 }],
    rejected: [
      {
        id: '00000000-0000-4000-8000-000000000003',
        reason: 'pressure_steps_mismatch',
      },
    ],
    flips: [
      {
        building_id: 4,
        from_team: null,
        to_team: 'AC',
        at: '2026-11-02T10:14:30Z',
      },
    ],
  };
export const rawStream: Schemas['Segment'] = {
  ...segment,
  // @ts-expect-error raw sensor streams never appear in a request
  pressure: [1013.2, 1012.8],
};
export const floorsInSegment: Schemas['Segment'] = {
  ...segment,
  // @ts-expect-error floors are not a game unit: segments carry steps and ascent only
  floors_gained: 3,
};
export const unknownReason: Schemas['RejectedSegment'] = {
  id: '00000000-0000-4000-8000-000000000003',
  // @ts-expect-error rejection reasons are a fixed list
  reason: 'floors_range',
};
export const floorInFlip: Schemas['BuildingFlip'] = {
  building_id: 4,
  from_team: 'ETC',
  to_team: 'AC',
  at: '2026-11-02T10:14:30Z',
  // @ts-expect-error a flip is per building, never per floor
  floor_no: 7,
};

// GET /buildings/{id}/standings
export const standings: paths['/buildings/{id}/standings']['get']['responses'][200]['content']['application/json'] =
  {
    building_id: 4,
    season_id: 1,
    owner: { id: 1, code: 'AC', color_hex: '#1E88E5' },
    claimed_at: '2026-11-02T10:14:30Z',
    window_start: '2026-10-26T10:15:00Z',
    teams: [
      { team_id: 1, code: 'AC', color_hex: '#1E88E5', points: 412 },
      { team_id: 2, code: 'ETC', color_hex: '#E53935', points: 390 },
    ],
  };
export const unclaimed: Schemas['BuildingStandings'] = {
  building_id: 5,
  season_id: 1,
  owner: null,
  claimed_at: null,
  teams: [],
};

// WebSocket events
export const flippedEvent: Schemas['WsEvent'] = {
  type: 'building_flipped',
  building_id: 4,
  from_team: 'ETC',
  to_team: 'AC',
  at: '2026-11-02T10:14:30Z',
};
export const seasonEvent: Schemas['WsEvent'] = {
  type: 'season_state',
  paused: false,
  ends_at: '2026-11-09T00:00:00Z',
};
export const oldFloorEvent: Schemas['WsEvent'] = {
  // @ts-expect-error floor_flipped was renamed building_flipped
  type: 'floor_flipped',
  building_id: 4,
  from_team: 'ETC',
  to_team: 'AC',
  at: '2026-11-02T10:14:30Z',
};

// GET /me/season-stats (steps-based; the floor-equivalent is computed in the app)
export const seasonStats: Schemas['SeasonStats'] = {
  season_id: 1,
  team_id: 1,
  steps_verified: 1240,
  ascent_m: 205.3,
  points: 1180,
  landmarks: [],
};

// POST /landing-scans (sticker at the stairs of a building, no floor)
export const landingScan: JsonBody<'/landing-scans', 'post'> = {
  qr_token: 'signed-sticker-token',
  building_id: 4,
};

// Typed client calls: these only need to compile; the runtime test below exercises one.
export async function typedCalls() {
  const tokens: Schemas['TokenPair'] = await api('post', '/auth/verify', {
    body: verifyRequest,
  });
  const result: Schemas['SegmentBatchResult'] = await api('post', '/segments', {
    header: segmentHeaders,
    body: batch,
  });
  const buildingStandings: Schemas['BuildingStandings'] = await api(
    'get',
    '/buildings/{id}/standings',
    { path: { id: 1 } },
  );
  return { tokens, result, buildingStandings };
}
