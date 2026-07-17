import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OtterWorks Demo Ops",
  description: "Ops dashboard for OtterWorks ephemeral demo tenants",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
