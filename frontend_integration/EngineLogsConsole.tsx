import { useState, useEffect, useRef } from "react";
import { Terminal, Shield, Play, Pause, Trash2, Search, ArrowDown, Copy, Check, Radio } from "lucide-react";

type LogEntry = {
  index: number;
  timestamp: string;
  level: "INFO" | "DEBUG" | "SUCCESS" | "WARNING" | "ERROR";
  message: string;
};

type Props = {
  client: any;
};

export function EngineLogsConsole({ client }: Props) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filterLevel, setFilterLevel] = useState<string>("ALL");
  const [searchText, setSearchText] = useState("");
  const [isLive, setIsLive] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [copied, setCopied] = useState(false);
  const [lastIndex, setLastIndex] = useState(-1);
  const [simulatedBlock, setSimulatedBlock] = useState<number | null>(null);

  const logsContainerRef = useRef<HTMLDivElement>(null);

  const lastIndexRef = useRef(lastIndex);

  // Sync ref with state
  useEffect(() => {
    lastIndexRef.current = lastIndex;
  }, [lastIndex]);

  // Poll for new logs from the backend
  useEffect(() => {
    let intervalId: any;

    const fetchLogs = async () => {
      try {
        const res = await client.getEngineLogs(lastIndexRef.current);
        if (res && res.ok) {
          if (res.currentBlock) {
            setSimulatedBlock(res.currentBlock);
          }
          if (res.logs && res.logs.length > 0) {
            setLogs(prev => {
              const existingIndices = new Set(prev.map(l => l.index));
              const newUniqueLogs = res.logs.filter((l: any) => !existingIndices.has(l.index));
              if (newUniqueLogs.length === 0) return prev;
              const combined = [...prev, ...newUniqueLogs];
              return combined.slice(-300);
            });
            // Update lastIndex to the highest log index we got
            const maxIdx = Math.max(...res.logs.map((l: any) => l.index));
            setLastIndex(maxIdx);
          }
        }
      } catch (err) {
        console.error("Failed to poll engine logs:", err);
      }
    };

    // Initial fetch
    fetchLogs();

    if (isLive) {
      intervalId = setInterval(fetchLogs, 1500);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [isLive, client]);

  // Handle user scrolling inside log terminal
  const handleScroll = () => {
    if (!logsContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    if (distanceFromBottom > 35) {
      setIsUserScrolledUp(true);
    } else {
      setIsUserScrolledUp(false);
      setUnreadCount(0);
      if (!autoScroll) {
        setAutoScroll(true);
      }
    }
  };

  // Scroll container smoothly when new logs arrive, strictly respecting user scroll state
  useEffect(() => {
    if (logs.length === 0 || !logsContainerRef.current) return;

    if (autoScroll && !isUserScrolledUp) {
      logsContainerRef.current.scrollTo({
        top: logsContainerRef.current.scrollHeight,
        behavior: "smooth"
      });
      setUnreadCount(0);
    } else if (isUserScrolledUp) {
      setUnreadCount(prev => prev + 1);
    }
  }, [logs]);

  const scrollToBottom = () => {
    setIsUserScrolledUp(false);
    setAutoScroll(true);
    setUnreadCount(0);
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTo({
        top: logsContainerRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  };

  const handleClear = () => {
    setLogs([]);
  };

  const handleCopy = () => {
    const text = logs.map(l => `[${new Date(l.timestamp).toLocaleTimeString()}] [${l.level}] ${l.message}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Filter logs locally based on level and search text
  const filteredLogs = logs.filter(log => {
    const matchesLevel = filterLevel === "ALL" || log.level === filterLevel;
    const matchesSearch = log.message.toLowerCase().includes(searchText.toLowerCase()) ||
                          log.level.toLowerCase().includes(searchText.toLowerCase());
    return matchesLevel && matchesSearch;
  });

  const getLogLevelStyle = (level: string) => {
    switch (level) {
      case "SUCCESS":
        return "text-emerald-400 font-bold";
      case "DEBUG":
        return "text-sky-400 font-medium";
      case "WARNING":
        return "text-amber-400 font-semibold";
      case "ERROR":
        return "text-rose-400 font-extrabold";
      default:
        return "text-slate-300";
    }
  };

  return (
    <div 
      id="engine-logs-console"
      className="bg-[#0b0f17] border border-[#1e293b] rounded-xl shadow-xl overflow-hidden flex flex-col h-[480px] relative"
    >
      {/* Console Header Bar */}
      <div className="bg-[#0e1624] border-b border-[#1e293b] px-4 py-3 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-slate-900 border border-emerald-500/30 rounded text-emerald-400">
            <Terminal className="w-4.5 h-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider font-mono">
                Omega Engine Live Execution Terminal
              </h3>
              <span className="flex h-2 w-2 relative">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isLive ? "bg-emerald-400" : "bg-amber-400"}`}></span>
                <span className={`relative inline-flex rounded-full h-2 w-2 ${isLive ? "bg-emerald-500" : "bg-amber-500"}`}></span>
              </span>
            </div>
            {simulatedBlock && (
              <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                Bor Head Sync: <span className="text-emerald-400 font-bold">#{simulatedBlock}</span> | Staging Window: <span className="text-sky-400">n+7 blocks</span>
              </p>
            )}
          </div>
        </div>

        {/* Live Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsLive(!isLive)}
            title={isLive ? "Pause stream" : "Resume stream"}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-semibold cursor-pointer border transition ${
              isLive 
                ? "bg-emerald-950/40 text-emerald-400 border-emerald-900/60 hover:bg-emerald-900/30" 
                : "bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800"
            }`}
          >
            {isLive ? (
              <>
                <Pause className="w-3.5 h-3.5" />
                Live Feed
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Paused
              </>
            )}
          </button>

          <button
            onClick={handleCopy}
            title="Copy entire log stream"
            className="p-1.5 bg-slate-900 hover:bg-slate-800 text-slate-400 border border-slate-800 rounded cursor-pointer transition"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={handleClear}
            title="Clear terminal logs"
            className="p-1.5 bg-slate-900 hover:bg-rose-950 hover:text-rose-400 hover:border-rose-900/40 text-slate-400 border border-slate-800 rounded cursor-pointer transition"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Console Filters and Search Controls */}
      <div className="bg-[#090d16] border-b border-[#1e293b]/70 px-4 py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shrink-0">
        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <span className="absolute inset-y-0 left-0 flex items-center pl-2.5 text-slate-500">
            <Search className="w-3.5 h-3.5" />
          </span>
          <input
            type="text"
            placeholder="Filter stream logs..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="w-full bg-[#0d131f] border border-[#1e293b] rounded pl-8 pr-3 py-1 text-xs text-slate-200 placeholder-slate-500 font-mono focus:outline-none focus:border-slate-700 focus:ring-1 focus:ring-slate-700"
          />
        </div>

        {/* Level Filters */}
        <div className="flex items-center gap-1 overflow-x-auto py-1 scrollbar-thin">
          {["ALL", "INFO", "DEBUG", "SUCCESS", "WARNING", "ERROR"].map((level) => (
            <button
              key={level}
              onClick={() => setFilterLevel(level)}
              className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-bold cursor-pointer transition whitespace-nowrap ${
                filterLevel === level
                  ? "bg-[#1e293b] text-slate-100 border border-[#334155]"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      {/* Scrollable Logs Output Screen */}
      <div 
        ref={logsContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed space-y-1.5 bg-[#070b12] scrollbar-thin relative"
      >
        {filteredLogs.length > 0 ? (
          filteredLogs.map((log, idx) => (
            <div 
              key={`log-${log.index}-${idx}`} 
              className="flex items-start gap-2 hover:bg-[#0c121e]/40 py-0.5 px-1 rounded transition duration-150"
            >
              {/* Timestamp */}
              <span className="text-slate-500 select-none shrink-0">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>

              {/* Level badge */}
              <span className={`shrink-0 select-none uppercase text-[9px] font-extrabold px-1 py-0.2 rounded border w-[52px] text-center ${
                log.level === "SUCCESS" ? "bg-emerald-950/20 text-emerald-400 border-emerald-900/30" :
                log.level === "DEBUG" ? "bg-sky-950/20 text-sky-400 border-sky-900/30" :
                log.level === "WARNING" ? "bg-amber-950/20 text-amber-400 border-amber-900/30" :
                log.level === "ERROR" ? "bg-rose-950/20 text-rose-400 border-rose-900/30" :
                "bg-slate-900 text-slate-400 border-slate-800"
              }`}>
                {log.level}
              </span>

              {/* Log Message */}
              <span className={`break-all ${getLogLevelStyle(log.level)}`}>
                {log.message}
              </span>
            </div>
          ))
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 py-10">
            <Radio className="w-8 h-8 text-slate-700 mb-2 animate-pulse" />
            <span className="text-xs">
              {searchText ? "No log matches found." : "Standby. Waiting for next block event logs..."}
            </span>
          </div>
        )}
      </div>

      {/* Floating Resume Auto-Scroll Button */}
      {isUserScrolledUp && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-12 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-[11px] shadow-xl border border-emerald-300 transition-all cursor-pointer animate-bounce"
        >
          <ArrowDown className="w-3.5 h-3.5" />
          <span>{unreadCount > 0 ? `${unreadCount} new logs below` : "Resume Auto-Scroll"}</span>
        </button>
      )}

      {/* Console Status Footer */}
      <div className="bg-[#080c13] border-t border-[#1e293b] px-4 py-2 flex items-center justify-between text-[10px] text-slate-500 font-mono shrink-0">
        <div className="flex items-center gap-3">
          <span>Staged Pool Limit: <strong className="text-slate-400">10 txs</strong></span>
          <span>Logs Cache: <strong className="text-slate-400">{filteredLogs.length} items</strong></span>
        </div>

        <label className="flex items-center gap-1.5 cursor-pointer hover:text-slate-300 transition select-none">
          <input
            type="checkbox"
            checked={autoScroll && !isUserScrolledUp}
            onChange={(e) => {
              if (e.target.checked) {
                scrollToBottom();
              } else {
                setAutoScroll(false);
                setIsUserScrolledUp(true);
              }
            }}
            className="rounded border-[#1e293b] bg-slate-900 text-emerald-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
          />
          <span>Auto-Scroll</span>
        </label>
      </div>
    </div>
  );
}
