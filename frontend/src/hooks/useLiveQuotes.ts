import { useEffect, useRef, useState } from "react";
import { ensureFreshAccessToken, quotesWebSocketUrl } from "../api/client";

export type LiveQuote = { price: number; changePercent: number | null };

type QuoteMessage = {
  type: string;
  quotes: Record<string, LiveQuote>;
};

/** Subscribes to the backend's near-real-time quote channel (docs/architecture.md
 * §4.1). Reconnects with a backoff; the dashboard keeps showing REST data while
 * the socket is down, so a dropped connection is never fatal.
 *
 * The token travels in the handshake URL, and an expired one gets the connection
 * rejected before it opens — there is no 401 to react to. So we refresh it ahead
 * of every attempt, which is what keeps the channel alive past the access
 * token's 15-minute lifetime. */
export function useLiveQuotes(enabled: boolean): Record<string, LiveQuote> {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function scheduleReconnect() {
      if (disposed) return;
      const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
      retryRef.current += 1;
      reconnectTimer = setTimeout(() => void connect(), delay);
    }

    async function connect() {
      if (disposed) return;
      if (!(await ensureFreshAccessToken())) {
        // The refresh token is gone or rejected; the API client already signalled
        // the expired session, so stop hammering the socket.
        return;
      }
      if (disposed) return;

      const socket = new WebSocket(quotesWebSocketUrl());
      socketRef.current = socket;

      socket.onopen = () => {
        retryRef.current = 0;
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data as string) as QuoteMessage;
          if (message.type === "quotes") {
            setQuotes((current) => ({ ...current, ...message.quotes }));
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = scheduleReconnect;
    }

    void connect();
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, [enabled]);

  return quotes;
}
