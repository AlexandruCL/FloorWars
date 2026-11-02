import {
  endSession,
  getAccessToken,
  getRefreshToken,
  saveTokens,
} from '../auth/session';
import type { paths } from './schema';

// The contract's servers entry. For the Prism mock, change it locally and do not commit that.
export const API_BASE_URL = 'https://api.floorwars.me/v1';

type Method = 'get' | 'post' | 'delete';
type Operation<P extends keyof paths, M extends Method> = NonNullable<
  paths[P][M]
>;
type Json<T> = T extends { content: { 'application/json': infer B } }
  ? B
  : undefined;
type OperationParameters<O> = O extends { parameters: infer X } ? X : never;
type RequestOptions<O> = {
  path?: OperationParameters<O> extends { path?: infer X } ? X : never;
  query?: OperationParameters<O> extends { query?: infer X } ? X : never;
  header?: OperationParameters<O> extends { header?: infer X } ? X : never;
  body?: O extends { requestBody?: infer R } ? Json<NonNullable<R>> : never;
};
type SuccessBody<O> = O extends { responses: infer R }
  ? Json<R[Extract<keyof R, 200 | 201 | 202 | 204>]>
  : never;

export class ApiError extends Error {
  constructor(readonly status: number, readonly problem: unknown) {
    super(`HTTP ${status}`);
  }
}

async function send(
  method: string,
  url: string,
  token: string | null,
  options: { header?: unknown; body?: unknown },
): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: 'application/json, application/problem+json',
    ...((options.header ?? {}) as Record<string, string>),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  return fetch(API_BASE_URL + url, {
    method: method.toUpperCase(),
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

async function parse(response: Response) {
  const text = await response.text();
  return text ? JSON.parse(text) : undefined;
}

let refreshing: Promise<void> | null = null;

// One refresh at a time: concurrent 401s await the same call, so a rotated token is never spent twice.
function refreshTokens(): Promise<void> {
  refreshing ??= (async () => {
    const refresh_token = await getRefreshToken();
    if (!refresh_token) {
      await endSession();
      throw new ApiError(401, undefined);
    }
    const response = await send('post', '/auth/refresh', null, {
      body: { refresh_token },
    });
    const data = await parse(response);
    if (response.status === 401) {
      // Unknown, expired or reused: the server has revoked the family, so the session is over.
      await endSession();
      throw new ApiError(401, data);
    }
    if (!response.ok) {
      throw new ApiError(response.status, data);
    }
    await saveTokens(data);
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

// Typed fetch over the generated contract types. Sends the stored access token as a bearer header.
// On a 401 it refreshes the tokens and retries once; /auth/* calls never trigger a refresh.
export async function api<P extends keyof paths, M extends Method>(
  method: M,
  path: P,
  options: RequestOptions<Operation<P, M>> = {},
): Promise<SuccessBody<Operation<P, M>>> {
  const pathParams = (options.path ?? {}) as Record<string, unknown>;
  let url = String(path).replace(/\{(\w+)\}/g, (_, name: string) =>
    encodeURIComponent(String(pathParams[name])),
  );
  const query = Object.entries((options.query ?? {}) as Record<string, unknown>)
    .filter(([, value]) => value !== undefined)
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`,
    )
    .join('&');
  if (query) {
    url += `?${query}`;
  }

  const token = await getAccessToken();
  let response = await send(method, url, token, options);
  if (response.status === 401 && token && !String(path).startsWith('/auth/')) {
    // If another call already rotated the tokens, just retry with the new one.
    if ((await getAccessToken()) === token) {
      await refreshTokens();
    }
    response = await send(method, url, await getAccessToken(), options);
  }
  const data = await parse(response);
  if (!response.ok) {
    throw new ApiError(response.status, data);
  }
  return data;
}
