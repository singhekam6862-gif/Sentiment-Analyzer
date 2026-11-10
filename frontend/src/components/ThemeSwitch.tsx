"use client";

import { type ReactNode, useEffect, useSyncExternalStore } from "react";

type Choice = "system" | "light" | "dark";
const CHOICES: Choice[] = ["system", "light", "dark"];
const LABEL: Record<Choice, string> = { system: "Auto (match device)", light: "Light", dark: "Dark" };
// Functional symbols, not decoration: each button's name is in aria-label and its tooltip.
const ICON: Record<Choice, ReactNode> = {
  system: (
    <>
      <circle cx="10" cy="10" r="6.5" />
      <path d="M10 3.5a6.5 6.5 0 0 1 0 13z" fill="currentColor" />
    </>
  ),
  light: (
    <>
      <circle cx="10" cy="10" r="3.5" />
      <path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6 16 16M4 16l1.4-1.4M14.6 5.4 16 4" />
    </>
  ),
  dark: <path d="M16.5 12.3A7 7 0 0 1 7.7 3.5a7 7 0 1 0 8.8 8.8z" />,
};
const CHANGED = "themechoice";

function apply(choice: Choice) {
  const dark = choice === "dark" || (choice === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  // Mobile browser toolbars match the header, whichever theme it's in.
  const masthead = getComputedStyle(document.documentElement).getPropertyValue("--color-masthead");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", masthead);
}

function readChoice(): Choice {
  try {
    const saved = localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGED, onChange);
  window.addEventListener("storage", onChange); // another tab changed it
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function pick(next: Choice) {
  try {
    if (next === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", next);
  } catch {
    // storage blocked: the choice still applies to this page
  }
  const change = () => {
    apply(next);
    window.dispatchEvent(new Event(CHANGED));
  };
  // Crossfades the whole page; browsers without view transitions just switch.
  if (!document.startViewTransition) return change();
  const fade = document.startViewTransition(change);
  // These reject if rendering stalls (a hidden tab, say). The theme still applies; only the fade is lost.
  fade.ready.catch(() => {});
  fade.updateCallbackDone.catch(() => {});
}

export function ThemeSwitch() {
  // null on the server and during hydration: only the browser knows the saved choice
  const choice = useSyncExternalStore(subscribe, readChoice, () => null);

  useEffect(() => {
    if (choice) apply(choice); // also catches a change made in another tab
    if (choice !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => apply("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [choice]);

  return (
    <div role="group" aria-label="Colour theme" className="flex rounded-full border border-field p-0.5 text-sm">
      {CHOICES.map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={choice === c}
          aria-label={LABEL[c]}
          title={LABEL[c]}
          onClick={() => pick(c)}
          className={`grid size-9 place-items-center rounded-full ${
            choice === c ? "bg-selected text-on-selected" : "text-masthead-muted hover:text-on-masthead"
          }`}
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" className="theme-icon size-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            {ICON[c]}
          </svg>
        </button>
      ))}
    </div>
  );
}
