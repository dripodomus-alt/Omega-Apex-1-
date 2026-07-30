import React, { useState, useRef, useEffect } from "react";
import { Bot, Send, Search as SearchIcon, Globe } from "lucide-react";
import { motion } from "motion/react";
import Markdown from "react-markdown";

interface AgentMessage {
  id: string;
  role: "user" | "model";
  message: string;
  timestamp: string;
  groundingWebUrls?: { title: string; uri: string }[];
}

export default function AgentTab({
  addLog,
}: {
  addLog: (tag: any, msg: string) => void;
}) {
  const [messages, setMessages] = useState<AgentMessage[]>([
    {
      id: "init",
      role: "model",
      message:
        "TITAN COPILOT ON-LINE. Connected to global network. Searching for current events, facts, or technical documentation. Awaiting query...",
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: AgentMessage = {
      id: crypto.randomUUID(),
      role: "user",
      message: input.trim(),
      timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    addLog("SYS", `TITAN COPILOT: Dispatching query...`);

    try {
      const res = await fetch("/api/gemini/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: userMessage.message,
          history: messages.slice(1), // exclude init message
        }),
      });

      const data = await res.json();

      if (data.success) {
        addLog("SYS", `TITAN COPILOT: Response received.`);

        let webUrls: { title: string; uri: string }[] = [];
        if (data.groundingChunks && data.groundingChunks.length > 0) {
          data.groundingChunks.forEach((chunk: any) => {
            if (chunk.web && chunk.web.uri) {
              webUrls.push({ title: chunk.web.title, uri: chunk.web.uri });
            }
          });
        }

        const modelMessage: AgentMessage = {
          id: crypto.randomUUID(),
          role: "model",
          message: data.text,
          timestamp: new Date().toLocaleTimeString("en-US", { hour12: false }),
          groundingWebUrls: webUrls,
        };
        setMessages((prev) => [...prev, modelMessage]);
      } else {
        addLog("ERR", `TITAN COPILOT: ${data.error}`);
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "model",
            message: `[ERROR] ${data.error}`,
            timestamp: new Date().toLocaleTimeString("en-US", {
              hour12: false,
            }),
          },
        ]);
      }
    } catch (err: any) {
      addLog("ERR", `TITAN COPILOT connection failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[400px] border border-[#1e2025] bg-[#0d0e12]/80 rounded-sm relative selection:bg-[#b388ff]/30 glass-specular glass-inset">
      <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-[#b388ff]/40" />
      <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-[#b388ff]/40" />

      <div className="flex items-center justify-between border-b border-[#1e2025]/60 p-3 shrink-0">
        <div className="flex items-center gap-2">
          <Bot size={14} className="text-[#b388ff]" />
          <h3 className="text-[10px] uppercase tracking-wider font-bold text-white">
            TITAN COPILOT
          </h3>
          <span className="ml-2 px-1.5 py-0.5 bg-[#b388ff]/10 text-[#b388ff] border border-[#b388ff]/20 rounded-sm text-[8px] uppercase font-bold flex items-center gap-1">
            <Globe size={8} /> LIVE WEB GROUNDED
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4 scrollbar-thin">
        {messages.map((msg, i) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`p-2.5 rounded-sm max-w-[85%] border ${
                msg.role === "user"
                  ? "bg-[#1e2025]/60 border-[#1e2025] text-gray-200"
                  : "bg-[#b388ff]/5 border-[#b388ff]/20 text-[#e2e8f0]"
              } text-[11px] leading-relaxed`}
            >
              <div className="flex items-center gap-2 mb-1.5 border-b border-white/5 pb-1 select-none">
                <span
                  className={`font-bold uppercase tracking-wider text-[8px] ${msg.role === "user" ? "text-gray-400" : "text-[#b388ff]"}`}
                >
                  {msg.role === "user" ? "OPERATOR" : "TITAN COPILOT"}
                </span>
                <span className="text-[7.5px] text-gray-500">
                  {msg.timestamp}
                </span>
              </div>

              <div className="font-sans text-[11px] leading-relaxed [&>p]:mb-2 [&>p:last-child]:mb-0 [&>ul]:list-disc [&>ul]:pl-4 [&>ul]:mb-2 [&>ol]:list-decimal [&>ol]:pl-4 [&>ol]:mb-2 [&>pre]:bg-black/50 [&>pre]:border [&>pre]:border-[#1e2025] [&>pre]:p-2 [&>pre]:rounded-sm [&>pre]:overflow-x-auto [&>code]:bg-[#1e2025] [&>code]:px-1 [&>code]:rounded-sm [&>a]:text-[#b388ff] [&>a]:underline">
                <Markdown>{msg.message}</Markdown>
              </div>

              {msg.groundingWebUrls && msg.groundingWebUrls.length > 0 && (
                <div className="mt-3 pt-2 border-t border-[#b388ff]/20">
                  <div className="text-[8px] uppercase tracking-wider text-[#b388ff]/70 font-bold mb-1.5 flex items-center gap-1">
                    <SearchIcon size={9} /> Sources
                  </div>
                  <div className="flex flex-col gap-1">
                    {msg.groundingWebUrls.map((url, idx) => (
                      <a
                        key={idx}
                        href={url.uri}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#b388ff] hover:text-[#d1b3ff] text-[9.5px] truncate hover:underline"
                        title={url.title}
                      >
                        {url.title}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        ))}
        {isLoading && (
          <div className="flex items-start">
            <div className="p-2.5 rounded-sm max-w-[85%] bg-[#b388ff]/5 border border-[#b388ff]/20">
              <div className="flex gap-1 animate-pulse">
                <div className="w-1.5 h-1.5 bg-[#b388ff] rounded-full" />
                <div className="w-1.5 h-1.5 bg-[#b388ff] rounded-full" />
                <div className="w-1.5 h-1.5 bg-[#b388ff] rounded-full" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-2 border-t border-[#1e2025] bg-black/40 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Query TITAN COPILOT... (Supports live web search)"
            className="flex-1 bg-black/60 border border-[#1e2025] focus:border-[#b388ff]/50 outline-none text-white px-3 py-2 text-[10px] font-mono rounded-sm"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-4 bg-[#b388ff]/10 hover:bg-[#b388ff]/20 border border-[#b388ff]/30 text-[#b388ff] transition-colors rounded-sm flex items-center justify-center disabled:opacity-50"
          >
            <Send size={14} />
          </button>
        </form>
      </div>
    </div>
  );
}
