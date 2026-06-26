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
  quickPrompts?: string[];
}

const T = {
  assistant: "\u5b66\u9662\u95ee\u7b54\u667a\u80fd\u4f53",
  emptyTitle: "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u4f60\uff1f",
  emptyDesc: "\u6211\u53ef\u4ee5\u57fa\u4e8e\u8ba1\u7b97\u673a\u5b66\u9662\u8d44\u6599\u56de\u7b54\u653f\u7b56\u3001\u6d41\u7a0b\u3001\u65f6\u95f4\u5b89\u6392\u548c\u5e38\u89c1\u95ee\u9898\u3002\u56de\u7b54\u7531 AI \u751f\u6210\uff0c\u8bf7\u4ed4\u7ec6\u7504\u522b\u3002",
  thinking: "\u6b63\u5728\u751f\u6210...",
  referencesPrefix: "\u53c2\u8003",
  referencesSuffix: "\u6761\u8d44\u6599\u6765\u6e90",
  copy: "\u590d\u5236",
  like: "\u8d5e\u540c",
  dislike: "\u4e0d\u8d5e\u540c",
};

const defaultPrompts = [
  "\u8ba1\u7b97\u673a\u5b66\u9662\u529e\u516c\u65f6\u95f4\u662f\u4ec0\u4e48\uff1f",
  "\u6bd5\u4e1a\u5b66\u5206\u8981\u6c42\u662f\u591a\u5c11\uff1f",
  "\u5b66\u9662\u6709\u54ea\u4e9b\u5e38\u89c1\u529e\u4e8b\u6d41\u7a0b\uff1f",
];

function CopyIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function ThumbIcon({ down = false }: { down?: boolean }) {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {down ? (
        <>
          <path d="M17 14V3" />
          <path d="M7 10v11" />
          <path d="M17 3h-5.4a2 2 0 0 0-1.8 1.1L7 10v11h9.7a2 2 0 0 0 2-1.7l.7-5A2 2 0 0 0 17.4 12H14" />
        </>
      ) : (
        <>
          <path d="M7 10v11" />
          <path d="M17 14V3" />
          <path d="M7 21h5.4a2 2 0 0 0 1.8-1.1L17 14V3H7.3a2 2 0 0 0-2 1.7l-.7 5A2 2 0 0 0 6.6 12H10" />
        </>
      )}
    </svg>
  );
}

function renderContent(content: string, streaming?: boolean) {
  if (!content && streaming) {
    return <p className="text-slate-500">{T.thinking}</p>;
  }

  return content.split("\n").map((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={index} className="h-3" />;

    const heading = trimmed.replace(/[\uff1a:]$/, "");
    const headings = [
      "\u6ce8\u610f\u4e8b\u9879",
      "\u4f9d\u636e",
      "\u53c2\u8003",
      "\u7ed3\u8bba",
      "\u8bf4\u660e",
      "\u529e\u7406\u65b9\u5f0f",
      "\u7533\u8bf7\u6761\u4ef6",
      "\u53c2\u8003\u51fa\u5904",
    ];
    const isHeading = headings.includes(heading);
    const isBullet = /^(?:[-*]|\u2022)\s+/.test(trimmed) || /^\d+[.\u3001]\s*/.test(trimmed);
    const text = trimmed.replace(/^(?:[-*]|\u2022)\s+/, "").replace(/^\d+[.\u3001]\s*/, "");

    if (isHeading) {
      return (
        <h2 key={index} className="mt-6 text-xl font-bold text-slate-950 first:mt-0">
          {heading}
        </h2>
      );
    }

    if (isBullet) {
      return (
        <p key={index} className="relative pl-7 text-lg leading-10 text-slate-800">
          <span className="absolute left-1 top-[0.95rem] h-2 w-2 rounded-full bg-slate-800" />
          {text}
        </p>
      );
    }

    return (
      <p key={index} className="text-lg leading-10 text-slate-800">
        {trimmed}
      </p>
    );
  });
}

export default function MessageList({ messages, onPromptClick, quickPrompts = defaultPrompts }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-10">
        <div className="w-full max-w-4xl text-center">
          <p className="text-sm font-semibold text-[#3f74f6]">{T.assistant}</p>
          <h2 className="mt-4 text-3xl font-bold text-slate-950 sm:text-4xl">{T.emptyTitle}</h2>
          <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-slate-500">{T.emptyDesc}</p>
          <div className="mt-9 grid gap-3 sm:grid-cols-3">
            {quickPrompts.map((prompt) => (
              <button key={prompt} type="button" onClick={() => onPromptClick?.(prompt)} className="min-h-24 rounded-lg border border-white/80 bg-white/90 px-5 py-4 text-left text-base font-semibold leading-6 text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-[#315fd8] hover:shadow-md">
                {prompt}
                <span className="mt-2 block text-sm font-normal text-slate-400">{T.assistant}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto px-4 py-10 sm:px-8 lg:px-14">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        {messages.map((msg) => {
          if (msg.role === "user") {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[78%] rounded-2xl bg-[#3f74f6] px-5 py-3 text-base leading-7 text-white shadow-sm">{msg.content}</div>
              </div>
            );
          }

          return (
            <article key={msg.id} className="max-w-5xl text-slate-900">
              <div className="space-y-1">{renderContent(msg.content, msg.streaming)}</div>

              {msg.streaming && (
                <span className="mt-4 inline-flex items-center gap-1.5 pl-1 text-slate-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400 [animation-delay:240ms]" />
                </span>
              )}

              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-7 border-t border-slate-200 pt-5">
                  <button type="button" className="inline-flex items-center gap-2 text-base font-semibold text-slate-500 hover:text-slate-800">
                    {T.referencesPrefix} {msg.citations.length} {T.referencesSuffix}
                    <span className="text-xl leading-none">?</span>
                  </button>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {msg.citations.slice(0, 4).map((c, i) => (
                      <div key={`${c.doc_id}-${i}`} className="rounded-lg bg-white/70 px-3 py-2 text-sm leading-6 text-slate-500">
                        <span className="mr-2 font-semibold text-slate-700">{c.doc_id}</span>
                        {c.snippet}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!msg.streaming && (
                <div className="mt-8 flex items-center gap-5 text-slate-500">
                  <button type="button" className="hover:text-slate-800" aria-label={T.copy} title={T.copy}><CopyIcon /></button>
                  <button type="button" className="hover:text-slate-800" aria-label={T.like} title={T.like}><ThumbIcon /></button>
                  <button type="button" className="hover:text-slate-800" aria-label={T.dislike} title={T.dislike}><ThumbIcon down /></button>
                </div>
              )}
            </article>
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}

