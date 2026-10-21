import { getAccessToken } from '../auth/authStub';
import type { paths } from './schema';

// Placeholder host from the contract's servers entry; replace when the server is deployed.
export const API_BASE_URL = 'https://api.example.invalid/v1';

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

// Typed fetch over the generated contract types. Sends the stored access token as a bearer header.
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

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...((options.header ?? {}) as Record<string, string>),
  };
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(API_BASE_URL + url, {
    method: method.toUpperCase(),
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!response.ok) {
    throw new ApiError(response.status, data);
  }
  return data;
}
