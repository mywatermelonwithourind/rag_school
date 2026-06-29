"use client";

import { ReactNode, useEffect, useRef, useState } from "react";

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

type MarkdownBlock =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: number; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; language: string; code: string };

const T = {
  assistant: "\u5b66\u9662\u95ee\u7b54\u667a\u80fd\u4f53",
  emptyTitle: "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u4f60\uff1f",
  emptyDesc: "\u6211\u53ef\u4ee5\u57fa\u4e8e\u8ba1\u7b97\u673a\u5b66\u9662\u8d44\u6599\u56de\u7b54\u653f\u7b56\u3001\u6d41\u7a0b\u3001\u65f6\u95f4\u5b89\u6392\u548c\u5e38\u89c1\u95ee\u9898\u3002\u56de\u7b54\u7531 AI \u751f\u6210\uff0c\u8bf7\u4ed4\u7ec6\u7504\u522b\u3002",
  thinking: "\u6b63\u5728\u751f\u6210...",
  referencesPrefix: "\u53c2\u8003",
  referencesSuffix: "\u6761\u8d44\u6599\u6765\u6e90",
  copy: "\u590d\u5236",
  copied: "\u5df2\u590d\u5236",
  copyFailed: "\u590d\u5236\u5931\u8d25",
  expandRefs: "\u5c55\u5f00\u53c2\u8003\u6765\u6e90",
  collapseRefs: "\u6536\u8d77\u53c2\u8003\u6765\u6e90",
  code: "\u4ee3\u7801",
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

function CodeIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="m8 9-4 3 4 3" />
      <path d="m16 9 4 3-4 3" />
      <path d="m14 5-4 14" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    const fence = trimmed.match(/^```\s*([^`]*)$/);
    if (fence) {
      const language = fence[1]?.trim() || "";
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ type: "code", language, code: codeLines.join("\n") });
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() });
      i += 1;
      continue;
    }

    const unordered = trimmed.match(/^(?:[-*]|\u2022)\s+(.+)$/);
    const ordered = trimmed.match(/^\d+[.\u3001]\s+(.+)$/);
    if (unordered || ordered) {
      const orderedList = !!ordered;
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i].trim();
        const currentUnordered = current.match(/^(?:[-*]|\u2022)\s+(.+)$/);
        const currentOrdered = current.match(/^\d+[.\u3001]\s+(.+)$/);
        if (orderedList && currentOrdered) items.push(currentOrdered[1].trim());
        else if (!orderedList && currentUnordered) items.push(currentUnordered[1].trim());
        else break;
        i += 1;
      }
      blocks.push({ type: "list", ordered: orderedList, items });
      continue;
    }

    const paragraphLines = [trimmed];
    i += 1;
    while (i < lines.length) {
      const next = lines[i].trim();
      if (!next || next.startsWith("```") || /^#{1,3}\s+/.test(next) || /^(?:[-*]|\u2022)\s+/.test(next) || /^\d+[.\u3001]\s+/.test(next)) {
        break;
      }
      paragraphLines.push(next);
      i += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${match.index}-bold`} className="font-semibold text-slate-950">{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={`${match.index}-code`} className="rounded-md bg-white px-1.5 py-0.5 font-mono text-[0.9em] text-slate-900">{token.slice(1, -1)}</code>);
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="my-5 overflow-hidden rounded-3xl border border-[#e5e7eb] bg-[#f7f7f7] shadow-sm">
      <div className="flex items-center justify-between border-b border-[#e5e7eb] px-5 py-3 text-slate-900">
        <div className="flex items-center gap-3 text-base font-medium">
          <CodeIcon />
          <span>{language || T.code}</span>
        </div>
        <button type="button" onClick={copyCode} className="rounded-lg p-1 text-slate-700 transition hover:bg-white hover:text-slate-950" aria-label={copied ? T.copied : T.copy} title={copied ? T.copied : T.copy}>
          <CopyIcon />
        </button>
      </div>
      <pre className="overflow-x-auto px-5 py-4 text-sm leading-7 text-slate-900"><code>{code}</code></pre>
    </div>
  );
}

function MarkdownContent({ content, streaming }: { content: string; streaming?: boolean }) {
  if (!content && streaming) return <p className="text-slate-500">{T.thinking}</p>;

  const blocks = parseMarkdown(content);
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const HeadingTag = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
          const headingClass = block.level === 1 ? "text-xl" : block.level === 2 ? "text-lg" : "text-base";
          return <HeadingTag key={index} className={`${headingClass} mt-4 font-bold leading-8 text-slate-950 first:mt-0`}>{renderInline(block.text)}</HeadingTag>;
        }

        if (block.type === "list") {
          const ListTag = block.ordered ? "ol" : "ul";
          return (
            <ListTag key={index} className={`space-y-1.5 pl-5 text-base leading-8 text-slate-800 ${block.ordered ? "list-decimal" : "list-disc"}`}>
              {block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}
            </ListTag>
          );
        }

        if (block.type === "code") {
          return <CodeBlock key={index} language={block.language} code={block.code} />;
        }

        return <p key={index} className="text-base leading-8 text-slate-800">{renderInline(block.text)}</p>;
      })}
    </div>
  );
}

export default function MessageList({ messages, onPromptClick, quickPrompts = defaultPrompts }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const [expandedRefs, setExpandedRefs] = useState<Record<string, boolean>>({});
  const [copyState, setCopyState] = useState<Record<string, "copied" | "failed">>({});

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const copyMessage = async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopyState((prev) => ({ ...prev, [id]: "copied" }));
    } catch {
      setCopyState((prev) => ({ ...prev, [id]: "failed" }));
    }

    window.setTimeout(() => {
      setCopyState((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }, 1800);
  };

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-8 sm:px-8">
        <div className="w-full max-w-3xl">
          <div className="text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#777]">{T.assistant}</p>
            <h2 className="mt-4 text-3xl font-semibold text-slate-950">{T.emptyTitle}</h2>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-slate-500">{T.emptyDesc}</p>
          </div>
          <div className="mx-auto mt-8 grid max-w-2xl gap-2">
            {quickPrompts.map((prompt) => (
              <button key={prompt} type="button" onClick={() => onPromptClick?.(prompt)} className="group flex min-h-14 items-center justify-between rounded-2xl border border-[#e8e8e8] bg-[#f7f7f7] px-5 py-3 text-left text-sm font-medium leading-6 text-slate-800 transition hover:border-[#d0d0d0] hover:bg-[#eeeeee]">
                <span className="truncate pr-4">{prompt}</span>
                <span className="shrink-0 text-lg leading-none text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-slate-700">→</span>
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
            const copied = copyState[msg.id] === "copied";
            const copyFailed = copyState[msg.id] === "failed";

            return (
              <div key={msg.id} className="flex items-end justify-end gap-2">
                <button
                  type="button"
                  onClick={() => void copyMessage(msg.id, msg.content)}
                  className={`relative mb-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all duration-200 ${
                    copied
                      ? "scale-110 bg-slate-900 text-white"
                      : copyFailed
                        ? "bg-slate-200 text-slate-900"
                        : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                  aria-label={copied ? T.copied : copyFailed ? T.copyFailed : T.copy}
                  title={copied ? T.copied : copyFailed ? T.copyFailed : T.copy}
                >
                  {copied && <span className="absolute inset-0 animate-ping rounded-full border border-slate-500" />}
                  <span className="relative">{copied ? <CheckIcon /> : <CopyIcon />}</span>
                </button>
                <div className="max-w-[72%] rounded-2xl border border-[#e5e7eb] bg-[#eeeeee] px-4 py-3 text-base leading-7 text-slate-950 shadow-sm">{msg.content}</div>
              </div>
            );
          }

          const refsOpen = !!expandedRefs[msg.id];
          const copied = copyState[msg.id] === "copied";
          const copyFailed = copyState[msg.id] === "failed";

          return (
            <article key={msg.id} className="max-w-4xl rounded-2xl border border-[#e5e7eb] bg-[#eeeeee] px-5 py-4 text-slate-900 shadow-sm">
              <MarkdownContent content={msg.content} streaming={msg.streaming} />

              {msg.streaming && msg.content && (
                <span className="mt-4 inline-flex items-center gap-1.5 pl-1 text-slate-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
                  <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400 [animation-delay:240ms]" />
                </span>
              )}

              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-5 border-t border-[#dedede] pt-4">
                  <button type="button" onClick={() => setExpandedRefs((prev) => ({ ...prev, [msg.id]: !prev[msg.id] }))} className="inline-flex items-center gap-2 text-base font-semibold text-slate-500 hover:text-slate-800" aria-expanded={refsOpen} title={refsOpen ? T.collapseRefs : T.expandRefs}>
                    {T.referencesPrefix} {msg.citations.length} {T.referencesSuffix}
                    <span className={`text-xl leading-none transition ${refsOpen ? "rotate-90" : ""}`}>{">"}</span>
                  </button>
                  {refsOpen && (
                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      {msg.citations.slice(0, 4).map((c, i) => (
                        <div key={`${c.doc_id}-${i}`} className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm leading-6 text-slate-500">
                          <span className="mr-2 font-semibold text-slate-700">{c.doc_id}</span>
                          {c.snippet}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {!msg.streaming && (
                <div className="mt-5 flex items-center text-slate-500">
                  <button type="button" onClick={() => void copyMessage(msg.id, msg.content)} className={`relative flex h-9 w-9 items-center justify-center rounded-full transition-all duration-200 hover:bg-white hover:text-slate-900 ${copied ? "scale-110 bg-slate-900 text-white hover:bg-slate-900 hover:text-white" : copyFailed ? "bg-slate-200 text-slate-900" : ""}`} aria-label={copied ? T.copied : copyFailed ? T.copyFailed : T.copy} title={copied ? T.copied : copyFailed ? T.copyFailed : T.copy}>
                    {copied && <span className="absolute inset-0 animate-ping rounded-full border border-slate-500" />}
                    <span className="relative">{copied ? <CheckIcon /> : <CopyIcon />}</span>
                  </button>
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
