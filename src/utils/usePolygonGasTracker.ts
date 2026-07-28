import { useState, useEffect, useRef, useCallback } from 'react';

export type GasConnectionType = 'ws' | 'rpc' | 'simulated';

export interface GasTrackerResult {
  gasGwei: number;
  connectionType: GasConnectionType;
  isLive: boolean;
  lastUpdated: string | null;
  trend: 'up' | 'down' | 'stable';
  gasHistory: number[];
  refetchGasPrice: () => Promise<void>;
  toggleConnectionMode: () => void;
}

const POLYGON_RPC_ENDPOINTS = [
  'https://polygon-rpc.com',
  'https://1rpc.io/matic',
  'https://rpc.ankr.com/polygon',
];

const POLYGON_WS_ENDPOINTS = [
  'wss://polygon-bor-rpc.publicnode.com',
  'wss://rpc-mainnet.matic.quiknode.pro',
];

export function usePolygonGasTracker(
  initialGwei: number = 38,
  onGasGweiUpdate?: (gwei: number) => void
): GasTrackerResult {
  const [gasGwei, setGasGwei] = useState<number>(initialGwei);
  const [connectionType, setConnectionType] = useState<GasConnectionType>('rpc');
  const [isLive, setIsLive] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [trend, setTrend] = useState<'up' | 'down' | 'stable'>('stable');
  const [gasHistory, setGasHistory] = useState<number[]>([initialGwei]);

  const wsRef = useRef<WebSocket | null>(null);
  const prevGasRef = useRef<number>(initialGwei);

  const updateGasState = useCallback((newGwei: number, type: GasConnectionType) => {
    const rounded = Math.max(15, Math.round(newGwei));
    const prev = prevGasRef.current;
    
    if (rounded > prev) {
      setTrend('up');
    } else if (rounded < prev) {
      setTrend('down');
    } else {
      setTrend('stable');
    }

    prevGasRef.current = rounded;
    setGasGwei(rounded);
    setConnectionType(type);
    setIsLive(true);
    setLastUpdated(new Date().toLocaleTimeString());

    setGasHistory((prevHist) => {
      const updated = [...prevHist, rounded];
      return updated.slice(-15); // keep last 15 ticks
    });

    if (onGasGweiUpdate) {
      onGasGweiUpdate(rounded);
    }
  }, [onGasGweiUpdate]);

  // Fetch gas price via Polygon HTTP JSON-RPC
  const fetchRpcGasPrice = useCallback(async () => {
    let fetched = false;

    for (const rpcUrl of POLYGON_RPC_ENDPOINTS) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);

        const response = await fetch(rpcUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'eth_gasPrice',
            params: [],
            id: 1,
          }),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (response.ok) {
          const data = await response.json();
          if (data && data.result) {
            const weiHex = data.result;
            const weiBig = BigInt(weiHex);
            const gweiVal = Number(weiBig / BigInt(1e9));
            if (!isNaN(gweiVal) && gweiVal > 0) {
              updateGasState(gweiVal, 'rpc');
              fetched = true;
              break;
            }
          }
        }
      } catch (err) {
        // Continue to fallback endpoint
      }
    }

    // Fallback if public RPC endpoints are blocked or failing
    if (!fetched) {
      // Generate realistic Polygon EIP-1559 base fee simulation (+/- 3 Gwei jitter around 32-55 Gwei)
      const baseJitter = (Math.random() - 0.48) * 6;
      const simulatedGwei = Math.max(18, Math.min(120, prevGasRef.current + baseJitter));
      updateGasState(simulatedGwei, 'simulated');
    }
  }, [updateGasState]);

  // Establish WebSocket connection to Polygon Bor Node
  const connectWebSocket = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {
        // ignore
      }
    }

    let wsConnected = false;
    const wsUrl = POLYGON_WS_ENDPOINTS[0];

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      const wsTimeout = setTimeout(() => {
        if (!wsConnected && ws.readyState !== WebSocket.OPEN) {
          ws.close();
          // Fall back to RPC polling if WS takes too long
          fetchRpcGasPrice();
        }
      }, 4000);

      ws.onopen = () => {
        wsConnected = true;
        clearTimeout(wsTimeout);
        // Subscribe to new block headers
        ws.send(
          JSON.stringify({
            jsonrpc: '2.0',
            id: 1,
            method: 'eth_subscribe',
            params: ['newHeads'],
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Block header received
          if (data && data.params && data.params.result) {
            const header = data.params.result;
            if (header.baseFeePerGas) {
              const baseFeeWei = BigInt(header.baseFeePerGas);
              const baseFeeGwei = Number(baseFeeWei / BigInt(1e9));
              // Priority fee buffer for Polygon ~30 Gwei
              const totalGasGwei = baseFeeGwei + 30;
              updateGasState(totalGasGwei, 'ws');
            } else {
              // Query RPC for explicit gas price on new block
              fetchRpcGasPrice();
            }
          }
        } catch (e) {
          // ignore parse error
        }
      };

      ws.onerror = () => {
        clearTimeout(wsTimeout);
        setIsLive(false);
        // Fall back to RPC on error
        fetchRpcGasPrice();
      };

      ws.onclose = () => {
        setIsLive(false);
      };
    } catch (err) {
      fetchRpcGasPrice();
    }
  }, [fetchRpcGasPrice, updateGasState]);

  // Periodic polling interval
  useEffect(() => {
    // Initial fetch
    fetchRpcGasPrice();

    // Set up 4-second periodic block/gas fetch interval
    const interval = setInterval(() => {
      if (connectionType === 'ws' && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        // WS is healthy and receiving events
        return;
      }
      fetchRpcGasPrice();
    }, 4500);

    return () => {
      clearInterval(interval);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (e) {
          // ignore
        }
      }
    };
  }, [fetchRpcGasPrice, connectionType]);

  const toggleConnectionMode = useCallback(() => {
    if (connectionType === 'ws') {
      if (wsRef.current) {
        wsRef.current.close();
      }
      fetchRpcGasPrice();
    } else {
      connectWebSocket();
    }
  }, [connectionType, connectWebSocket, fetchRpcGasPrice]);

  return {
    gasGwei,
    connectionType,
    isLive,
    lastUpdated,
    trend,
    gasHistory,
    refetchGasPrice: fetchRpcGasPrice,
    toggleConnectionMode,
  };
}
