import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request } from './api.js';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('request', () => {
  it('returns records and accepts an empty array', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ id: 4 }] }).mockResolvedValueOnce({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal('fetch', fetchMock);
    await expect(request('/api/plants')).resolves.toEqual([{ id: 4 }]);
    await expect(request('/api/plants')).resolves.toEqual([]);
  });

  it('turns HTTP failures into ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: 'db unavailable' }) }));
    try { await request('/api/plants'); throw new Error('Expected request to fail'); }
    catch (error) { expect(error).toBeInstanceOf(ApiError); expect(error.status).toBe(503); expect(error.message).toBe('The server could not complete this request. Please try again.'); }
  });

  it('reports a request timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((url, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))));
    const pending = request('/api/plants');
    const outcome = pending.then((value) => value, (error) => error);
    await vi.advanceTimersByTimeAsync(20_000);
    const error = await outcome;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(408);
  });

  it('preserves caller cancellation', async () => {
    const controller = new AbortController();
    vi.stubGlobal('fetch', vi.fn((url, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))));
    const pending = request('/api/plants', { signal: controller.signal });
    controller.abort();
    const error = await pending.then((value) => value, (reason) => reason);
    expect(error.name).toBe('AbortError');
  });
});
