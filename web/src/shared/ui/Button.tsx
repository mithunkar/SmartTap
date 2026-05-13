import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

type ButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    fullWidth?: boolean;
  }
>;

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-forest text-sand shadow-soft hover:bg-[#1f4033] disabled:bg-[#95a89f] disabled:shadow-none",
  secondary:
    "bg-white/80 text-ink ring-1 ring-border hover:bg-white disabled:text-ink/50 disabled:bg-white/60",
  ghost: "bg-transparent text-ink/80 hover:bg-white/60",
};

export function Button({
  children,
  className = "",
  variant = "primary",
  fullWidth = false,
  ...props
}: ButtonProps) {
  return (
    <button
      className={[
        "rounded-full px-4 py-2.5 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-forest/40",
        variantClasses[variant],
        fullWidth ? "w-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      {children}
    </button>
  );
}
