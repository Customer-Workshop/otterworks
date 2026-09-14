import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Otter Projects",
  description: "Minimal issue tracker with Devin ticket assignment",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
