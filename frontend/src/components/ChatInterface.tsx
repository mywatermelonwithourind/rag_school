"use client";

import { FormEvent, useCallback, useRef, useState } from "react";
import MessageList, { Citation, Message } from "./MessageList";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

function uid() {
  return Math.random().toString(36).slice(2);
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      const question = input.trim();
      if (!question || loading) return;

      const userMsg: Message = {
        id: uid(),
        role: "user",
        content: question,
      };
      const assistantId = uid();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setLoading(true);

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      try {
        const res = await fetch(`${API_BASE}/api/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question,
            session_id: sessionId,
          }),
          signal: abortRef.current.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullAnswer = "";
        let citations: Citation[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            try {
              const event = JSON.parse(raw);
              if (event.type === "token") {
                fullAnswer += event.content;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: fullAnswer }
                      : m
                  )
                );
              } else if (event.type === "citations") {
                citations = event.content;
              } else if (event.type === "done") {
                if (event.session_id) setSessionId(event.session_id);
                if (event.answer) fullAnswer = event.answer;
              }
            } catch {
              /* ignore malformed SSE chunk */
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: fullAnswer || "（无回答）",
                  citations,
                  streaming: false,
                }
              : m
          )
        );
      } catch (err) {
        const msg =
          err instanceof Error && err.name === "AbortError"
            ? "请求已取消"
            : `请求失败：${err instanceof Error ? err.message : "未知错误"}`;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: msg, streaming: false }
              : m
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [input, loading, sessionId]
  );

  return (
    <div className="flex min-h-[70vh] flex-1 flex-col rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
      <MessageList messages={messages} />
      <form
        onSubmit={sendMessage}
        className="flex gap-2 border-t border-slate-100 p-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入您的问题…"
          disabled={loading}
          className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "发送中…" : "发送"}
        </button>
      </form>
    </div>
  );
}
