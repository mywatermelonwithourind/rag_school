"use client";

import { FormEvent, KeyboardEvent, useCallback, useMemo, useRef, useState } from "react";
import MessageList, { Citation, Message } from "./MessageList";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const T = {
  appTitle: "\u8ba1\u7b97\u673a\u5b66\u9662\u667a\u80fd\u95ee\u7b54\u7cfb\u7edf",
  subtitle: "\u9762\u5411\u5b66\u9662\u653f\u7b56\u3001\u6d41\u7a0b\u548c\u8d44\u6599\u7684\u667a\u80fd\u95ee\u7b54\u52a9\u624b \u00b7 \u5185\u5bb9\u7531 AI \u751f\u6210\uff0c\u8bf7\u4ed4\u7ec6\u7504\u522b",
  assistant: "\u5b66\u9662\u95ee\u7b54\u667a\u80fd\u4f53",
  newChat: "\u65b0\u5efa\u5bf9\u8bdd",
  unifiedChat: "\u7edf\u4e00\u5bf9\u8bdd",
  knowledge: "\u77e5\u8bc6\u56fe\u8c31",
  search: "\u641c\u7d22\u4f1a\u8bdd",
  total: "\u4f1a\u8bdd\u603b\u6570",
  recent: "\u6700\u8fd1\u5bf9\u8bdd",
  all: "\u5168\u90e8",
  collapse: "\u6536\u8d77\u4fa7\u680f",
  expand: "\u5c55\u5f00\u4fa7\u680f",
  create: "\u65b0\u5efa",
  placeholder: "\u8f93\u5165\u60a8\u7684\u95ee\u9898...",
  stop: "\u505c\u6b62\u751f\u6210",
  send: "\u53d1\u9001",
  noAnswer: "\uff08\u65e0\u56de\u7b54\uff09",
  canceled: "\u8bf7\u6c42\u5df2\u53d6\u6d88",
  failed: "\u8bf7\u6c42\u5931\u8d25",
  unknown: "\u672a\u77e5\u9519\u8bef",
  noResults: "\u6ca1\u6709\u5339\u914d\u7684\u4f1a\u8bdd",
  noRecent: "\u6682\u65e0\u5bf9\u8bdd\u8bb0\u5f55",
  graphTitle: "\u5b66\u9662\u8d44\u6599\u77e5\u8bc6\u56fe\u8c31",
  graphDesc: "\u6309\u8d44\u6599\u7c7b\u578b\u548c\u5e38\u89c1\u95ee\u9898\u7ec4\u7ec7\uff0c\u7528\u4e8e\u5feb\u901f\u5b9a\u4f4d\u653f\u7b56\u3001\u6d41\u7a0b\u3001\u65f6\u95f4\u548c\u529e\u4e8b\u6750\u6599\u3002",
};

const seedPrompts = [
  "\u8ba1\u7b97\u673a\u5b66\u9662\u529e\u516c\u65f6\u95f4\u662f\u4ec0\u4e48\uff1f",
  "\u6bd5\u4e1a\u5b66\u5206\u8981\u6c42\u662f\u591a\u5c11\uff1f",
  "\u5b66\u9662\u6709\u54ea\u4e9b\u5e38\u89c1\u529e\u4e8b\u6d41\u7a0b\uff1f",
];

const graphNodes = [
  "\u5b66\u9662\u653f\u7b56",
  "\u529e\u4e8b\u6d41\u7a0b",
  "\u6559\u52a1\u57f9\u517b",
  "\u5956\u52a9\u8bc4\u5b9a",
  "\u65f6\u95f4\u5b89\u6392",
  "\u5e38\u89c1\u95ee\u9898",
];

type IconName = "plus" | "chat" | "book" | "search" | "panel" | "edit" | "send" | "stop";
type ActiveView = "chat" | "knowledge";

interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  backendSessionId: string | null;
  updatedAt: number;
}

function uid() {
  return Math.random().toString(36).slice(2);
}

function titleFromQuestion(question: string) {
  return question.length > 22 ? `${question.slice(0, 22)}...` : question;
}

function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  const common = {
    className: `h-5 w-5 ${className}`,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "plus":
      return <svg {...common}><path d="M12 5v14" /><path d="M5 12h14" /></svg>;
    case "chat":
      return <svg {...common}><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" /><path d="m9 12 2 2 4-5" /></svg>;
    case "book":
      return <svg {...common}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" /></svg>;
    case "search":
      return <svg {...common}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>;
    case "panel":
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></svg>;
    case "edit":
      return <svg {...common}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>;
    case "send":
      return <svg {...common}><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>;
    case "stop":
      return <svg {...common}><rect x="7" y="7" width="10" height="10" rx="1" /></svg>;
  }
}

function KnowledgeGraph() {
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-10">
      <div className="w-full max-w-5xl">
        <div className="text-center">
          <p className="text-sm font-semibold text-[#111827]">{T.knowledge}</p>
          <h2 className="mt-4 text-3xl font-bold text-slate-950 sm:text-4xl">{T.graphTitle}</h2>
          <p className="mx-auto mt-4 max-w-3xl text-base leading-7 text-slate-500">{T.graphDesc}</p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {graphNodes.map((node) => (
            <button key={node} type="button" className="min-h-28 rounded-lg border border-[#e5e7eb] bg-white px-5 py-4 text-left shadow-sm transition hover:border-[#d1d5db] hover:text-[#111827] hover:shadow-md">
              <span className="block text-lg font-semibold text-slate-800">{node}</span>
              <span className="mt-2 block text-sm leading-6 text-slate-500">{T.assistant}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatInterface() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [searchTerm, setSearchTerm] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? null,
    [activeConversationId, conversations]
  );
  const messages = activeConversation?.messages ?? [];

  const recentConversations = useMemo(
    () => [...conversations].sort((a, b) => b.updatedAt - a.updatedAt),
    [conversations]
  );

  const filteredConversations = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return recentConversations;
    return recentConversations.filter((conversation) => conversation.title.toLowerCase().includes(keyword));
  }, [recentConversations, searchTerm]);

  const updateConversation = (conversationId: string, updater: (conversation: Conversation) => Conversation) => {
    setConversations((prev) => prev.map((conversation) => (conversation.id === conversationId ? updater(conversation) : conversation)));
  };

  const submitQuestion = useCallback(async (value?: string) => {
    const question = (value ?? input).trim();
    if (!question || loading) return;

    setActiveView("chat");

    const conversationId = activeConversation?.id ?? uid();
    const backendSessionId = activeConversation?.backendSessionId ?? null;
    const userMsg: Message = { id: uid(), role: "user", content: question };
    const assistantId = uid();
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", streaming: true };

    if (!activeConversation) {
      setConversations((prev) => [
        {
          id: conversationId,
          title: titleFromQuestion(question),
          messages: [userMsg, assistantMsg],
          backendSessionId: null,
          updatedAt: Date.now(),
        },
        ...prev,
      ]);
      setActiveConversationId(conversationId);
    } else {
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        messages: [...conversation.messages, userMsg, assistantMsg],
        updatedAt: Date.now(),
      }));
    }

    setInput("");
    setLoading(true);
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: backendSessionId }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullAnswer = "";
      let citations: Citation[] = [];
      let nextBackendSessionId = backendSessionId;

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
              updateConversation(conversationId, (conversation) => ({
                ...conversation,
                messages: conversation.messages.map((message) =>
                  message.id === assistantId ? { ...message, content: fullAnswer } : message
                ),
                updatedAt: Date.now(),
              }));
            } else if (event.type === "citations") {
              citations = event.content;
            } else if (event.type === "done") {
              if (event.session_id) nextBackendSessionId = event.session_id;
              if (event.answer) fullAnswer = event.answer;
            }
          } catch {
            // Ignore malformed SSE chunks and keep the stream alive.
          }
        }
      }

      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        backendSessionId: nextBackendSessionId,
        messages: conversation.messages.map((message) =>
          message.id === assistantId
            ? { ...message, content: fullAnswer || T.noAnswer, citations, streaming: false }
            : message
        ),
        updatedAt: Date.now(),
      }));
    } catch (err) {
      const msg = err instanceof Error && err.name === "AbortError" ? T.canceled : `${T.failed}: ${err instanceof Error ? err.message : T.unknown}`;
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        messages: conversation.messages.map((message) =>
          message.id === assistantId ? { ...message, content: msg, streaming: false } : message
        ),
        updatedAt: Date.now(),
      }));
    } finally {
      setLoading(false);
    }
  }, [activeConversation, input, loading]);

  const sendMessage = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    await submitQuestion();
  }, [submitQuestion]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submitQuestion();
    }
  };

  const startNewChat = () => {
    abortRef.current?.abort();
    setActiveConversationId(null);
    setInput("");
    setLoading(false);
    setActiveView("chat");
  };

  const openConversation = (conversationId: string) => {
    abortRef.current?.abort();
    setActiveConversationId(conversationId);
    setInput("");
    setLoading(false);
    setActiveView("chat");
  };

  return (
    <div className="flex h-dvh overflow-hidden bg-white text-slate-900">
      {sidebarOpen && (
        <aside className="hidden w-[clamp(260px,18vw,330px)] shrink-0 flex-col border-r border-[#e5e7eb] bg-white px-3 py-4 shadow-[1px_0_0_rgba(17,24,39,0.10)] lg:flex">
          <div className="mb-5 flex h-10 items-center justify-end px-4">
            <button type="button" onClick={() => setSidebarOpen(false)} className="flex h-9 w-9 items-center justify-center rounded-full text-slate-400 transition hover:bg-[#f3f4f6] hover:text-slate-700" aria-label={T.collapse} title={T.collapse}>
              <span className="text-2xl leading-none">&lt;</span>
            </button>
          </div>

          <button type="button" onClick={startNewChat} className="flex h-11 w-full items-center justify-start gap-3 rounded-lg bg-[#111827] px-5 text-base font-medium text-white shadow-sm transition hover:bg-black">
            <Icon name="plus" />
            {T.newChat}
          </button>

          <nav className="mt-3 space-y-1">
            <button type="button" onClick={() => setActiveView("chat")} className={`flex h-11 w-full items-center gap-3 rounded-lg px-4 text-left text-base transition ${activeView === "chat" ? "bg-[#f3f4f6] font-semibold text-[#111827]" : "font-medium text-slate-600 hover:bg-[#f3f4f6]"}`}>
              <Icon name="chat" />
              {T.unifiedChat}
            </button>
            <button type="button" onClick={() => setActiveView("knowledge")} className={`flex h-11 w-full items-center gap-3 rounded-lg px-4 text-left text-base transition ${activeView === "knowledge" ? "bg-[#f3f4f6] font-semibold text-[#111827]" : "font-medium text-slate-600 hover:bg-[#f3f4f6]"}`}>
              <Icon name="book" />
              {T.knowledge}
            </button>
          </nav>

          <label className="mt-5 flex h-11 items-center gap-3 rounded-lg border border-[#e5e7eb] bg-white px-4 text-slate-400 shadow-sm focus-within:border-[#9ca3af] focus-within:ring-4 focus-within:ring-[#f3f4f6]">
            <Icon name="search" className="text-slate-400" />
            <input type="search" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder={T.search} className="min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400" />
          </label>

          <div className="mt-3 rounded-lg bg-[#f9fafb] px-4 py-3 text-sm text-slate-500">
            {T.total}: {conversations.length}
          </div>

          <div className="mt-4 flex min-h-0 flex-1 flex-col">
            <div className="mb-2 flex items-center justify-between px-3 text-sm text-slate-500">
              <span>{T.recent}</span>
              <button type="button" onClick={() => setSearchTerm("")} className="font-medium text-[#111827] hover:text-black">{T.all}</button>
            </div>
            <div className="min-h-0 space-y-1 overflow-y-auto pr-1">
              {conversations.length === 0 ? (
                <p className="px-3 py-3 text-sm text-slate-400">{T.noRecent}</p>
              ) : filteredConversations.length === 0 ? (
                <p className="px-3 py-3 text-sm text-slate-400">{T.noResults}</p>
              ) : (
                filteredConversations.map((conversation) => (
                  <button key={conversation.id} type="button" onClick={() => openConversation(conversation.id)} className={`w-full rounded-lg px-3 py-2.5 text-left transition ${conversation.id === activeConversationId ? "bg-[#f3f4f6]" : "hover:bg-[#f3f4f6]"}`}>
                    <span className="block truncate text-base font-semibold text-slate-800">{conversation.title}</span>
                    <span className="mt-1 block text-sm text-slate-400">{T.assistant}</span>
                  </button>
                ))
              )}
            </div>
          </div>
        </aside>
      )}

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-20 shrink-0 items-center border-b border-[#e5e7eb] bg-white px-5">
          <div className="flex w-24 items-center gap-4 text-slate-500">
            <button type="button" onClick={() => setSidebarOpen((open) => !open)} className="hidden h-10 w-10 items-center justify-center rounded-lg hover:bg-[#f3f4f6] lg:flex" aria-label={sidebarOpen ? T.collapse : T.expand} title={sidebarOpen ? T.collapse : T.expand}><Icon name="panel" /></button>
            <button type="button" onClick={startNewChat} className="hidden h-10 w-10 items-center justify-center rounded-lg hover:bg-[#f3f4f6] lg:flex" aria-label={T.create} title={T.create}><Icon name="edit" /></button>
            <button type="button" onClick={startNewChat} className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-[#f3f4f6] lg:hidden" aria-label={T.create} title={T.create}><Icon name="plus" /></button>
          </div>

          <div className="mx-auto min-w-0 px-4 text-center">
            <h1 className="truncate text-xl font-bold text-slate-950">{T.appTitle}</h1>
            <p className="mt-2 truncate text-sm font-medium text-slate-500">{T.subtitle}</p>
          </div>

          <div className="w-24 shrink-0" />
        </header>

        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
          {activeView === "knowledge" ? (
            <KnowledgeGraph />
          ) : (
            <MessageList messages={messages} onPromptClick={(prompt) => void submitQuestion(prompt)} quickPrompts={seedPrompts} />
          )}

          {activeView === "chat" && (
            <div className="shrink-0 bg-white px-3 pb-4 pt-2 sm:px-6 lg:px-10">
              <form onSubmit={sendMessage} className="mx-auto flex min-h-[96px] w-full max-w-[min(980px,calc(100vw-3rem))] items-end gap-3 rounded-2xl border border-[#e5e7eb] bg-white p-4 shadow-[0_18px_45px_rgba(17,24,39,0.10)] focus-within:ring-4 focus-within:ring-[#f3f4f6]">
                <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder={T.placeholder} disabled={loading} rows={2} className="max-h-36 min-h-14 flex-1 resize-none bg-transparent text-lg leading-7 text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-50" />
                {loading ? (
                  <button type="button" onClick={() => abortRef.current?.abort()} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-[#e5e7eb] bg-white text-slate-600 transition hover:bg-[#f3f4f6]" aria-label={T.stop} title={T.stop}><Icon name="stop" /></button>
                ) : (
                  <button type="submit" disabled={!input.trim()} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#111827] text-white shadow-sm transition hover:bg-black disabled:cursor-not-allowed disabled:bg-slate-300" aria-label={T.send} title={T.send}><Icon name="send" className="h-6 w-6" /></button>
                )}
              </form>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
