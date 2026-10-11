/**
 * Server-sent-event helper that works in both builds.
 *
 * Real deployments open an `EventSource` against the backend. Demo builds have
 * no backend to stream from, so the same call is served by a simulated emitter
 * (imported lazily, so demo fixtures never reach a production bundle).
 */

import { authUrl } from './api';
import { DEMO_MODE } from './app-config';

export interface StreamHandlers {
  /** Called once the stream is established. */
  onOpen?: () => void;
  /** Called with the raw event payload for each message. */
  onMessage?: (raw: string) => void;
  /** Called when the stream drops (the caller decides whether to reconnect). */
  onError?: () => void;
}

export interface StreamHandle {
  close(): void;
}

/** Open a live server-sent-event stream for a backend path such as `/dashboard/stream`. */
export function openStream(path: string, handlers: StreamHandlers): StreamHandle {
  if (DEMO_MODE) return openDemoStream(path, handlers);

  const source = new EventSource(authUrl(path));
  source.onopen = () => handlers.onOpen?.();
  source.onmessage = (event) => handlers.onMessage?.(event.data);
  source.onerror = () => handlers.onError?.();
  return { close: () => source.close() };
}

function openDemoStream(path: string, handlers: StreamHandlers): StreamHandle {
  let closed = false;
  const disposers: Array<() => void> = [];

  void import('./demo').then(({ demoStream }) => {
    if (closed) return;
    demoStream(path, handlers, (dispose) => disposers.push(dispose));
  });

  return {
    close() {
      closed = true;
      for (const dispose of disposers) dispose();
      disposers.length = 0;
    },
  };
}
