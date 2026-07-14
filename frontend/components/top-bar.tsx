"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Analyze" },
  { href: "/history", label: "History" },
  { href: "/eval", label: "Eval" },
];

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 flex h-[52px] flex-none items-center justify-between border-b border-line bg-bg px-[18px]">
      <div className="flex items-center gap-[26px]">
        <div className="flex items-center gap-[9px]">
          <div className="flex h-5 w-5 items-center justify-center rounded-[2px] bg-accent text-[12px] font-semibold text-bg">
            V
          </div>
          <span className="text-[13px] font-semibold tracking-[0.04em]">
            VERDICT ANALYST
          </span>
          <span className="border-l border-line pl-[11px] font-mono text-[11px] text-faint">
            causal analytics agent
          </span>
        </div>
        <nav className="flex items-center gap-[2px]">
          {NAV.map((n) => {
            const active =
              n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "rounded-[2px] px-3 py-[5px] text-[12px] transition-colors",
                  active
                    ? "bg-panel text-ink"
                    : "text-faint hover:text-ink",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-[10px] font-mono text-[11px] text-faint">
        <span>sandbox</span>
        <span className="text-accent">ready</span>
        <span className="text-[#2a2a2a]">|</span>
        <span>gemini-2.0-flash</span>
        <span className="text-[#2a2a2a]">·</span>
        <span>duckdb</span>
      </div>
    </header>
  );
}
