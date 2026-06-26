import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "\u8ba1\u7b97\u673a\u5b66\u9662\u667a\u80fd\u95ee\u7b54\u7cfb\u7edf",
  description: "RAG \u8bfe\u7a0b\u9879\u76ee - \u804a\u5929\u754c\u9762",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
