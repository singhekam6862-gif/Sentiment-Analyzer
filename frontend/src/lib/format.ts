export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * Whole percent of n in total, or null under 10 reviews, where a percentage would overstate thin evidence (SPEC §A.1).
 * Shows 0 or 100 only when exact: 49 of 50,000 is not "0%".
 */
export const percent = (n: number, total: number): number | null =>
  total < 10 ? null : Math.min(Math.max(Math.round((n / total) * 100), n > 0 ? 1 : 0), n < total ? 99 : 100);

export const stars =(n: number) => "★★★★★".slice(0, n) + "☆☆☆☆☆".slice(0, 5 - n);

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
