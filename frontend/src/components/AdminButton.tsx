import type { ButtonHTMLAttributes } from "react";
import { useAdmin } from "../context/AdminContext";

const ADMIN_HINT = "관리자 로그인이 필요합니다";

export default function AdminButton({
  disabled,
  title,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { isAdmin } = useAdmin();
  const blocked = !isAdmin;
  return (
    <button
      {...rest}
      disabled={disabled || blocked}
      title={blocked ? ADMIN_HINT : title}
      className={`${className ?? ""} disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {children}
    </button>
  );
}

/** 비관리자에게만 보이는 안내 배너. */
export function AdminNotice() {
  const { isAdmin } = useAdmin();
  if (isAdmin) return null;
  return (
    <div className="mb-6 rounded-lg border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
      관리 기능을 사용하려면 우측 상단에서 관리자 로그인이 필요합니다.
    </div>
  );
}
