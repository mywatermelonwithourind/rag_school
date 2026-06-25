import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "计算机学院智能问答系统",
  description: "RAG 课程项目 — 聊天界面",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
