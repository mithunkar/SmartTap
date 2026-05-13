import type { HTMLAttributes, PropsWithChildren } from "react";

type PanelProps = PropsWithChildren<
  HTMLAttributes<HTMLDivElement> & {
    title?: string;
    subtitle?: string;
  }
>;

export function Panel({ children, className = "", title, subtitle, ...props }: PanelProps) {
  return (
    <section
      className={[
        "rounded-shell border border-border bg-card p-5 shadow-soft backdrop-blur",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      {(title || subtitle) && (
        <header className="mb-4">
          {title ? <h2 className="font-display text-xl text-ink">{title}</h2> : null}
          {subtitle ? <p className="mt-1 text-sm text-ink/70">{subtitle}</p> : null}
        </header>
      )}
      {children}
    </section>
  );
}
