"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Analyze" },
  { href: "/history", label: "History" },
  { href: "/eval", label: "Eval" },
];

const REPO_URL = "https://github.com/ne-he/agentic_verdict";

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 flex h-[52px] flex-none items-center justify-between gap-3 border-b border-line bg-bg px-[14px] md:px-[18px]">
      <div className="flex min-w-0 items-center gap-3 md:gap-[26px]">
        <div className="flex flex-none items-center gap-[9px]">
          <div className="flex h-5 w-5 flex-none items-center justify-center rounded-[2px] bg-accent text-[12px] font-semibold text-bg">
            V
          </div>
          <span className="whitespace-nowrap text-[13px] font-semibold tracking-[0.04em]">
            VERDICT ANALYST
          </span>
          <span className="hidden border-l border-line pl-[11px] font-mono text-[11px] text-faint md:inline">
            causal analytics agent
          </span>
        </div>
        {/* Di layar sempit nav scroll di dalam dirinya sendiri, bukan halaman. */}
        <nav className="no-scrollbar flex min-w-0 items-center gap-[2px] overflow-x-auto">
          {NAV.map((n) => {
            const active =
              n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex-none whitespace-nowrap rounded-[2px] px-2 py-[5px] text-[12px] transition-colors md:px-3",
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
      <div className="flex flex-none items-center gap-[10px] font-mono text-[11px] text-faint">
        <div className="hidden items-center gap-[10px] lg:flex">
          <span>sandbox</span>
          <span className="text-accent">ready</span>
          <span className="text-[#2a2a2a]">|</span>
          <span>gemini-2.0-flash</span>
          <span className="text-[#2a2a2a]">·</span>
          <span>duckdb</span>
          <span className="text-[#2a2a2a]">|</span>
        </div>
        <a
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="Source code di GitHub"
          aria-label="Source code on GitHub"
          className="flex items-center gap-[6px] transition-colors hover:text-ink"
        >
          <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          <span className="hidden md:inline">source</span>
        </a>
      </div>
    </header>
  );
}
