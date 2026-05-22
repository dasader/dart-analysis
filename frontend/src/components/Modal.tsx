import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** 패널 최대 너비 Tailwind 클래스 (기본 max-w-md) */
  widthClass?: string;
}

/** 오버레이 + 패널 + 헤더(타이틀·닫기)를 제공하는 공용 모달 래퍼. */
export default function Modal({ title, onClose, children, widthClass = "max-w-md" }: ModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className={`w-full ${widthClass} rounded-xl border border-border bg-surface p-6 shadow-xl`}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          <button onClick={onClose} className="btn-close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
