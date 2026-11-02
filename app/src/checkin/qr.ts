// Entrance token: fwq1.<b64url(payload)>.<b64url(HMAC)>. The server owns the HMAC check; the app
// only reads exp to avoid a pointless round trip for a code that is plainly out of date.
// Hermes provides atob; the RN TypeScript config does not declare it.
declare function atob(data: string): string;

const TOKEN_RE = /^fwq1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const MAX_TOKEN_LEN = 512;

export type QrParse =
  | { ok: true; token: string; expired: boolean }
  | { ok: false };

export function parseQrPayload(raw: string, nowMs = Date.now()): QrParse {
  const token = raw.trim();
  if (token.length > MAX_TOKEN_LEN || !TOKEN_RE.test(token)) {
    return { ok: false };
  }
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(
      atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, '=')),
    );
    if (typeof payload?.exp !== 'number') {
      return { ok: false };
    }
    // shortcut: trusts the phone clock, so a wrong clock shows "expired"; scan again after fixing it.
    return { ok: true, token, expired: payload.exp * 1000 < nowMs };
  } catch {
    return { ok: false };
  }
}
