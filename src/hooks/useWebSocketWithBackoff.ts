import { useEffect, useRef, useState, useCallback } from 'react';

export function useWebSocketWithBackoff(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [errorCount, setErrorCount] = useState(0);
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectDelay = 30000; // 30 seconds
  const timeoutId = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    try {
      if (ws.current) {
         if (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING) {
             return;
         }
         ws.current.onclose = null;
         ws.current.onerror = null;
         ws.current.onmessage = null;
         ws.current.onopen = null;
         ws.current.close();
      }

      const socket = new WebSocket(url);
      ws.current = socket;

      socket.onopen = () => {
        setIsConnected(true);
        reconnectAttempts.current = 0;
        console.log(`[WebSocket] Connected to ${url}`);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);
        } catch (e) {
          setLastMessage(event.data);
        }
      };

      socket.onclose = (event) => {
        setIsConnected(false);
        console.warn(`[WebSocket] Closed: code ${event.code} reason ${event.reason}`);
        
        // Exponential backoff strategy with jitter
        const baseDelay = Math.min(1000 * Math.pow(1.5, reconnectAttempts.current), maxReconnectDelay);
        const jitter = 100; // Mock random replaced
        const delay = baseDelay + jitter;
        
        reconnectAttempts.current += 1;
        setErrorCount(reconnectAttempts.current);
        
        console.log(`[WebSocket] Reconnecting in ${Math.round(delay)}ms (Attempt ${reconnectAttempts.current})`);
        
        if (timeoutId.current) {
            clearTimeout(timeoutId.current);
        }
        
        timeoutId.current = setTimeout(connect, delay);
      };

      socket.onerror = (error) => {
        console.error(`[WebSocket] Error: `, error);
        socket.close(); // Force the onClose handler to trigger backoff
      };
    } catch (err) {
      console.error(`[WebSocket] Connection failed immediately`, err);
      const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts.current), maxReconnectDelay);
      reconnectAttempts.current += 1;
      setErrorCount(reconnectAttempts.current);
      if (timeoutId.current) {
          clearTimeout(timeoutId.current);
      }
      timeoutId.current = setTimeout(connect, delay);
    }
  }, [url]);

  useEffect(() => {
    connect();

    return () => {
      if (timeoutId.current) {
        clearTimeout(timeoutId.current);
      }
      if (ws.current) {
        ws.current.onclose = null; // Prevent reconnect logic when unmounting
        ws.current.onerror = null;
        ws.current.onmessage = null;
        ws.current.onopen = null;
        ws.current.close();
        ws.current = null;
      }
    };
  }, [connect]);

  return { isConnected, lastMessage, errorCount };
}
