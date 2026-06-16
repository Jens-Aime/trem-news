import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className = "" }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-slate-800 bg-slate-900 shadow-lg ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  children,
  className = "",
}: CardProps) {
  return (
    <div className={`rounded-t-lg px-4 py-3 ${className}`}>{children}</div>
  );
}

export function CardContent({ children, className = "" }: CardProps) {
  return <div className={`px-4 py-3 ${className}`}>{children}</div>;
}
