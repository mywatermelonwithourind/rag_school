"use client";

import { FormEvent, KeyboardEvent, useCallback, useRef, useState } from "react";
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

  const submitQuestion = useCallback(
    async (value?: string) => {
      const question = (value ?? input).trim();
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
          const { done, value: chunk } = await reader.read();
          if (done) break;

          buffer += decoder.decode(chunk, { stream: true });
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
                    m.id === assistantId ? { ...m, content: fullAnswer } : m
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
            m.id === assistantId ? { ...m, content: msg, streaming: false } : m
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [input, loading, sessionId]
  );

  const sendMessage = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      await submitQuestion();
    },
    [submitQuestion]
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submitQuestion();
    }
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
  };

  const startNewChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setInput("");
    setSessionId(null);
    setLoading(false);
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl gap-4 p-3 md:p-5">
      <aside className="hidden w-72 shrink-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:flex">
        <div className="flex items-center gap-3 border-b border-slate-100 pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-sm font-semibold text-white">
            CS
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-950">学院问答智能体</p>
            <p className="mt-0.5 text-xs text-slate-500">RAG · SSE · Knowledge QA</p>
          </div>
        </div>

        <button
          type="button"
          onClick={startNewChat}
          className="mt-4 flex h-10 items-center justify-center rounded-xl bg-slate-950 px-3 text-sm font-medium text-white transition hover:bg-slate-800"
        >
          + 新对话
        </button>

        <div className="mt-5 space-y-2">
          <p className="px-1 text-xs font-medium uppercase tracking-wide text-slate-400">
            常用入口
          </p>
          {["办公时间", "学分要求", "办事流程"].map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => void submitQuestion(item)}
              disabled={loading}
              className="block w-full rounded-xl px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 disabled:opacity-50"
            >
              {item}
            </button>
          ))}
        </div>

        <div className="mt-auto rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-800">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            服务状态
          </div>
          <p className="text-xs leading-5 text-slate-500">
            前端默认连接 {API_BASE}，后端启动后即可流式回答。
          </p>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header className="flex min-h-16 items-center justify-between border-b border-slate-100 px-4 md:px-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-base font-semibold text-slate-950 md:text-lg">
                计算机学院智能问答系统
              </h1>
              <span className="hidden rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 md:inline-flex">
                在线
              </span>
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">
              面向学院政策、流程和资料的智能问答助手
            </p>
          </div>
          <button
            type="button"
            onClick={startNewChat}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 lg:hidden"
          >
            新对话
          </button>
        </header>

        <MessageList
          messages={messages}
          onPromptClick={(prompt) => void submitQuestion(prompt)}
        />

        <div className="border-t border-slate-100 bg-white p-3 md:p-4">
          <form
            onSubmit={sendMessage}
            className="mx-auto flex max-w-4xl items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 shadow-sm transition focus-within:border-blue-300 focus-within:bg-white focus-within:ring-4 focus-within:ring-blue-50"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入您的问题..."
              disabled={loading}
              rows={1}
              className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-5 text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-50"
            />
            {loading ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="h-11 shrink-0 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                停止
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-lg font-semibold text-white shadow-sm shadow-blue-100 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                aria-label="发送"
              >
                ↑
              </button>
            )}
          </form>
          <p className="mt-2 text-center text-xs text-slate-400">
            Enter 发送，Shift + Enter 换行
          </p>
        </div>
      </section>
    </div>
  );
}
