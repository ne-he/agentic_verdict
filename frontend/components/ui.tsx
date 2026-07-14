/** Primitive UI ringan bergaya shadcn (cn-based). Cukup untuk MVP ANALYST. */
import * as React from "react";
import { cn } from "@/lib/utils";

export function Panel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border border-line bg-bg", className)} {...props} />;
}

export function SectionLabel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "text-[10px] uppercase tracking-[0.14em] text-faint",
        className,
      )}
      {...props}
    />
  );
}

export function Mono({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("font-mono", className)} {...props} />;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "solid" | "ghost" | "outline";
};

export function Button({
  className,
  variant = "outline",
  ...props
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 text-[11px] font-mono transition-colors disabled:cursor-not-allowed disabled:opacity-40";
  const styles = {
    solid: "bg-accent text-bg hover:opacity-90",
    ghost: "text-muted hover:text-ink",
    outline:
      "border border-line2 text-muted hover:border-accent hover:text-accent rounded-[2px] px-3 py-1",
  } as const;
  return <button className={cn(base, styles[variant], className)} {...props} />;
}

/** Bar progres tipis 0..1. */
export function Bar({
  value,
  className,
  fill = "bg-accent",
}: {
  value: number;
  className?: string;
  fill?: string;
}) {
  const w = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className={cn("h-[3px] w-full bg-[#1a1a1a]", className)}>
      <div className={cn("h-full", fill)} style={{ width: `${w}%` }} />
    </div>
  );
}
