"use client";

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
}

export default function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
        请输入问题，例如：「计算机学院办公时间是什么」
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-2">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
              msg.role === "user"
                ? "bg-blue-600 text-white"
                : "bg-white shadow-sm ring-1 ring-slate-200"
            }`}
          >
            <p className="whitespace-pre-wrap">{msg.content}</p>
            {msg.streaming && (
              <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-slate-400" />
            )}
            {msg.citations && msg.citations.length > 0 && (
              <div className="mt-3 border-t border-slate-100 pt-2">
                <p className="mb-1 text-xs font-medium text-slate-500">参考出处</p>
                <ul className="space-y-1">
                  {msg.citations.map((c, i) => (
                    <li key={i} className="text-xs text-slate-600">
                      <span className="font-mono text-slate-400">
                        [{c.doc_id}]
                      </span>{" "}
                      {c.snippet}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
