import { createContext, useContext, useState, type ReactNode } from "react";
import { verifyAdminKey } from "../api/client";
import { getAdminKey, setAdminKey, clearAdminKey } from "../lib/adminKey";

interface AdminContextValue {
  isAdmin: boolean;
  login: (key: string) => Promise<boolean>;
  logout: () => void;
}

const AdminContext = createContext<AdminContextValue | null>(null);

export function AdminProvider({ children }: { children: ReactNode }) {
  // 저장된 키가 있으면 관리자 상태로 시작(요청 시 401이면 재로그인 유도)
  const [isAdmin, setIsAdmin] = useState<boolean>(() => getAdminKey() !== null);

  const login = async (key: string): Promise<boolean> => {
    const ok = await verifyAdminKey(key);
    if (ok) {
      setAdminKey(key);
      setIsAdmin(true);
    }
    return ok;
  };

  const logout = () => {
    clearAdminKey();
    setIsAdmin(false);
  };

  return (
    <AdminContext.Provider value={{ isAdmin, login, logout }}>
      {children}
    </AdminContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdmin(): AdminContextValue {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin must be used within AdminProvider");
  return ctx;
}
