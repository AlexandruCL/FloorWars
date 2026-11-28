// k6 load test (W5-8): batched POST /v1/segments with fresh Idempotency-Keys across many test
// users, plus N WebSockets receiving flips. LOCAL STACK ONLY (see README.md); never the VM.
//
//   k6 run -e BASE_URL=http://localhost:8080 -e USERS=users.json load.js
//   k6 run -e SCENARIO=smoke ...        (1 user, a few requests: checks the script)
//
// Each seeded user may send 60 uploads an hour (a full bucket at start), so the arrival
// scenario stops at MAX_PER_USER = 50 requests per user. Access tokens last 15 minutes.
import http from 'k6/http';
import ws from 'k6/ws';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const WS_BASE = BASE.replace(/^http/, 'ws');
const data = JSON.parse(open(__ENV.USERS || 'users.json'));
const users = new SharedArray('users', () => data.users);
const building = data.building_id;
const smoke = __ENV.SCENARIO === 'smoke';
const MAX_PER_USER = 50;
const PEAK_RPS = Number(__ENV.PEAK_RPS || 60);
const SOCKETS = Number(__ENV.SOCKETS || 100);
const SEGMENTS_PER_BATCH = 3;

const accepted = new Counter('fw_segments_accepted');
const rejected = new Counter('fw_segments_rejected');
const flips = new Counter('fw_flip_frames');
const sockets = new Counter('fw_sockets_opened');

export const options = smoke
  ? { vus: 1, iterations: 3 }
  : {
      scenarios: {
        uploads: {
          executor: 'ramping-arrival-rate',
          exec: 'upload',
          startRate: 5,
          timeUnit: '1s',
          preAllocatedVUs: 50,
          maxVUs: 300,
          stages: [
            { target: PEAK_RPS / 2, duration: '1m' },
            { target: PEAK_RPS, duration: '3m' },
            { target: 0, duration: '30s' },
          ],
        },
        sockets: {
          executor: 'per-vu-iterations',
          exec: 'listen',
          vus: SOCKETS,
          iterations: 1,
          maxDuration: '6m',
        },
      },
      thresholds: {
        'http_req_failed{scenario:uploads}': ['rate<0.02'],
        'http_req_duration{scenario:uploads}': ['p(95)<500'],
      },
    };

export function upload() {
  // Iteration n of the whole test: user n % N, its (n / N)-th request.
  const n = smoke ? __ITER : exec.scenario.iterationInTest;
  const user = users[n % users.length];
  const seq = Math.floor(n / users.length);
  if (seq >= MAX_PER_USER) return;
  const now = Date.now();
  const segments = [];
  for (let j = 0; j < SEGMENTS_PER_BATCH; j++) {
    // one climb per minute backwards: no overlap, 30 steps each (under the 600 per 10 min cap)
    const at = new Date(now - (seq * SEGMENTS_PER_BATCH + j + 2) * 60000).toISOString();
    segments.push({
      id: uuidv4(), checkin_id: user.checkin_id, building_id: building, started_at: at,
      ascent_m: 6.0, duration_s: 30.0, vert_speed_mps: 0.2, steps: 30, stair_prob: 0.9,
      classifier_version: 'rules-1',
    });
  }
  const res = http.post(`${BASE}/v1/segments`,
    JSON.stringify({ device_id: user.device_id, segments }),
    { headers: { Authorization: `Bearer ${user.token}`, 'Content-Type': 'application/json',
                 'Idempotency-Key': uuidv4() }, tags: { name: 'POST /v1/segments' } });
  check(res, { 'status 200': (r) => r.status === 200 });
  if (res.status === 200) {
    const body = res.json();
    accepted.add(body.accepted.length);
    rejected.add(body.rejected.length);
  }
}

export function listen() {
  const user = users[(exec.vu.idInTest - 1) % users.length];
  const url = `${WS_BASE}/v1/ws?since=0&access_token=${user.token}`;
  const res = ws.connect(url, {}, (socket) => {
    socket.on('open', () => sockets.add(1));
    socket.on('message', () => flips.add(1));
    // hold for the length of the upload scenario, then leave
    socket.setTimeout(() => socket.close(), smoke ? 5000 : 270000);
  });
  check(res, { 'ws 101': (r) => r && r.status === 101 });
}
