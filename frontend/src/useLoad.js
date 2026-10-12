import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_POLL_MS = Math.max(30_000, Number(import.meta.env.VITE_POLL_INTERVAL_MS) || 60_000);
const SLOW_AFTER_MS = 8_000;

export function useLoad(loader, dependencies = [], pollInterval = DEFAULT_POLL_MS) {
  const [state, setState] = useState({ data: null, loading: true, slow: false, error: '' });
  const activeRequest = useRef(null);
  const generation = useRef(0);
  const effectSignal = useRef(null);
  const stableLoader = useCallback(loader, dependencies);

  const reload = useCallback((options = {}) => {
    const force = options?.force === true;
    const signal = options instanceof AbortSignal ? options : effectSignal.current;
    if (signal?.aborted) return Promise.resolve(null);
    const active = activeRequest.current;
    if (active && !active.signal?.aborted) {
      if (!force) return active.promise;
      active.controller.abort();
    }

    const requestGeneration = ++generation.current;
    const controller = new AbortController();
    const abortFromEffect = () => controller.abort();
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener('abort', abortFromEffect, { once: true });
    }
    setState((previous) => ({ ...previous, loading: true, slow: false, error: '' }));
    const slowTimer = window.setTimeout(() => {
      if (generation.current === requestGeneration) setState((previous) => ({ ...previous, slow: true }));
    }, SLOW_AFTER_MS);

    const promise = (async () => {
      try {
        const data = await stableLoader(controller.signal);
        if (generation.current === requestGeneration) setState({ data, loading: false, slow: false, error: '' });
        return data;
      } catch (error) {
        if (generation.current === requestGeneration) {
          if (error.name === 'AbortError') setState((previous) => ({ ...previous, loading: false, slow: false }));
          else setState((previous) => ({ ...previous, loading: false, slow: false, error: error.message || 'Could not load records.' }));
        }
        return null;
      } finally {
        window.clearTimeout(slowTimer);
        signal?.removeEventListener('abort', abortFromEffect);
        if (activeRequest.current?.generation === requestGeneration) activeRequest.current = null;
      }
    })();

    activeRequest.current = { generation: requestGeneration, signal: controller.signal, controller, promise };
    return promise;
  }, [stableLoader]);

  useEffect(() => {
    const controller = new AbortController();
    effectSignal.current = controller.signal;
    reload();
    const timer = pollInterval > 0 ? window.setInterval(() => {
      if (!document.hidden) reload(controller.signal);
    }, pollInterval) : null;
    return () => {
      controller.abort();
      if (effectSignal.current === controller.signal) effectSignal.current = null;
      if (timer) window.clearInterval(timer);
    };
  }, [reload, pollInterval]);

  return { ...state, reload };
}
