import ChatInterface from "@/components/ChatInterface";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col p-4">
      <header className="mb-4 border-b border-slate-200 pb-4">
        <h1 className="text-xl font-semibold text-slate-800">
          计算机学院智能问答系统
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          课程项目骨架 — SSE 流式对话
        </p>
      </header>
      <ChatInterface />
    </main>
  );
}
