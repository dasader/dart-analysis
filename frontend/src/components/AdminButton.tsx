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
