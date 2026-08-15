import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { fetchExtractionFailures, fetchSchedulerStatus } from "../api/client";
import type { SchedulerStatus } from "../types";
import { useAdmin } from "../context/AdminContext";

export default function Layout() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [failureCount, setFailureCount] = useState(0);

  // 스케줄러 가동 여부는 거의 변하지 않으므로 마운트 시 1회만 조회
  useEffect(() => {
    fetchSchedulerStatus().then(setScheduler).catch(() => {});
  }, []);

  // 구역 추출 실패는 보고서 서식 변경 신호 — 어느 화면에 있든 눈에 띄어야 한다
  useEffect(() => {
    const check = () =>
      fetchExtractionFailures()
        .then((f) => setFailureCount(f.length))
        .catch(() => {});
    check();
    const timer = setInterval(check, 60000);
    return () => clearInterval(timer);
  }, []);

  const { isAdmin, login, logout } = useAdmin();

  const handleLogin = async () => {
    const key = window.prompt("관리자 키를 입력하세요");
    if (!key) return;
    const ok = await login(key);
    if (!ok) alert("관리자 키가 올바르지 않습니다.");
  };

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
            <Link to="/technologies" className="nav-link">
              기술
            </Link>
            <Link to="/settings/batches" className="nav-link">
              분석 현황
              {failureCount > 0 && (
                <span
                  title={`구역 추출 실패 ${failureCount}건 — 보고서 서식 확인 필요`}
                  className="ml-1.5 rounded-full bg-amber-400 px-1.5 py-0.5 text-xs font-semibold text-amber-950"
                >
                  {failureCount}
                </span>
              )}
            </Link>
            <Link to="/tags" className="nav-link">
              태그 관리
            </Link>
            <Link
              to="/settings/prompts"
              className="nav-link"
            >
              설정
            </Link>
            {isAdmin ? (
              <button onClick={logout} className="nav-link">
                관리자 로그아웃
              </button>
            ) : (
              <button onClick={handleLogin} className="nav-link">
                관리자 로그인
              </button>
            )}
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
