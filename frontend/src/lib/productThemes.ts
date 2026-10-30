// Colour per compared product, by position: first product cyan, second amber.
export const PRODUCT_THEMES = [
  {
    hex: "#06b6d4",
    text: "text-cyan-400",
    border: "border-cyan-500/30",
    badge: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
    dot: "bg-cyan-500",
    bar: "bg-cyan-500",
  },
  {
    hex: "#f59e0b",
    text: "text-amber-400",
    border: "border-amber-500/30",
    badge: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
  },
] as const;
