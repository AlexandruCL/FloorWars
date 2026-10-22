import { signInWithStub, DUMMY_ACCESS_TOKEN } from '../src/auth/authStub';
import { api, API_BASE_URL, ApiError } from '../src/api/client';
import { batch, batchResult, segmentHeaders } from './contract/samples';

function mockFetch(ok: boolean, status: number, body: unknown) {
  const fetchMock = jest.fn(async () => ({
    ok,
    status,
    text: async () => JSON.stringify(body),
  }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

test('api() calls the contract path with the stub token and JSON body', async () => {
  await signInWithStub(() => {});
  const fetchMock = mockFetch(true, 200, batchResult);
  await expect(
    api('post', '/segments', { header: segmentHeaders, body: batch }),
  ).resolves.toEqual(batchResult);
  expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/segments`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Idempotency-Key': 'batch-1',
      Authorization: `Bearer ${DUMMY_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(batch),
  });
});

test('api() fills path parameters and throws ApiError with the problem body on 4xx', async () => {
  const problem = { title: 'Not Found', status: 404 };
  const fetchMock = mockFetch(false, 404, problem);
  const call = api('get', '/buildings/{id}/standings', { path: { id: 99 } });
  await expect(call).rejects.toBeInstanceOf(ApiError);
  await expect(call).rejects.toMatchObject({ status: 404, problem });
  expect(fetchMock.mock.calls[0]).toEqual(
    expect.arrayContaining([`${API_BASE_URL}/buildings/99/standings`]),
  );
});
