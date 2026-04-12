import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { fetchSchedulerStatus } from "../api/client";
import type { SchedulerStatus } from "../types";

export default function Layout() {
  const location = useLocation();
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);

  useEffect(() => {
    fetchSchedulerStatus().then(setScheduler).catch(() => {});
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Navigation */}
      <header className="no-print sticky top-0 z-50 border-b border-border bg-navy text-white shadow-sm">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link
            to="/"
            className="flex items-center gap-2.5 font-semibold tracking-tight transition-opacity hover:opacity-80"
          >
            <span className="text-lg">DART</span>
            <span className="text-sm font-normal text-white/60">
              기업 사업보고서 분석
            </span>
          </Link>

          <div className="flex items-center gap-4 text-sm">
            {scheduler && (
              <div className="flex items-center gap-1.5">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    scheduler.is_running ? "bg-green-400" : "bg-red-400"
                  }`}
                />
                <span className="text-white/60">
                  {scheduler.is_running ? "스케줄러 동작중" : "스케줄러 정지"}
                </span>
              </div>
            )}
            <Link
              to="/settings/prompts"
              className="nav-link"
            >
              설정
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="no-print mt-4 border-t border-border">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <span className="text-xs font-medium text-text-tertiary">
            DART 기업 사업보고서 분석
          </span>
          <span className="font-mono text-xs text-text-tertiary">
            v{__APP_VERSION__}
          </span>
        </div>
      </footer>
    </div>
  );
}
