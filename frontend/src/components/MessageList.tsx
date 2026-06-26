"use client";

import { useEffect, useRef } from "react";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
}

export interface Citation {
  parent_chunk_id: string;
  doc_id: string;
  snippet: string;
  relevance_score: number;
}

interface MessageListProps {
  messages: Message[];
  onPromptClick?: (prompt: string) => void;
}

const quickPrompts = [
  "计算机学院办公时间是什么？",
  "毕业学分要求是多少？",
  "学院有哪些常见办事流程？",
];

export default function MessageList({
  messages,
  onPromptClick,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-4 py-8">
        <div className="w-full max-w-2xl text-center">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-950 text-lg font-semibold text-white shadow-lg shadow-slate-200">
            AI
          </div>
          <h2 className="text-2xl font-semibold tracking-normal text-slate-950">
            有什么可以帮你？
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-500">
            我可以基于计算机学院资料回答政策、流程、时间安排和常见问题。
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onPromptClick?.(prompt)}
                className="min-h-20 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm leading-5 text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-6 md:px-8">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex items-start gap-3 ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          {msg.role === "assistant" && (
            <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-950 text-xs font-semibold text-white">
              AI
            </div>
          )}
          <div
            className={`max-w-[86%] rounded-2xl px-4 py-3 text-sm leading-7 shadow-sm md:max-w-[72%] ${
              msg.role === "user"
                ? "rounded-tr-md bg-blue-600 text-white shadow-blue-100"
                : "rounded-tl-md border border-slate-200 bg-white text-slate-800"
            }`}
          >
            <p className="whitespace-pre-wrap break-words">
              {msg.content || (msg.streaming ? "正在思考..." : "")}
            </p>
            {msg.streaming && (
              <span className="mt-2 inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400 [animation-delay:240ms]" />
              </span>
            )}
            {msg.citations && msg.citations.length > 0 && (
              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="mb-2 text-xs font-medium text-slate-500">参考出处</p>
                <ul className="space-y-2">
                  {msg.citations.map((c, i) => (
                    <li
                      key={i}
                      className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600"
                    >
                      <span className="mr-1 font-mono text-slate-400">
                        [{c.doc_id}]
                      </span>
                      {c.snippet}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {msg.role === "user" && (
            <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
              我
            </div>
          )}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
