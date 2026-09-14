"use client";

import ReactMarkdown from "react-markdown";

export default function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`prose-md text-sm leading-relaxed ${className}`}>
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
