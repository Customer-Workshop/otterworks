"use client";

import { type ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { SearchBar } from "@/components/ui/search-bar";
import { NotificationBell } from "@/components/ui/notification-bell";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import { Menu } from "lucide-react";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const { sidebarOpen, toggleSidebar } = useUIStore();

  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar />

      <div
        className={cn(
          "transition-all duration-200",
          sidebarOpen ? "lg:ml-64" : "lg:ml-16"
        )}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-30 bg-white border-b border-gray-200 h-16">
          <div className="flex items-center justify-between h-full px-4 lg:px-6">
            <div className="flex items-center gap-3 flex-1">
              <button
                onClick={toggleSidebar}
                className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 lg:hidden"
                aria-label="Open menu"
              >
                <Menu size={20} />
              </button>
              <div className="w-full max-w-xl">
                <SearchBar />
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <NotificationBell />
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
