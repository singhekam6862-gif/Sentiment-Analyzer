"use client";

import { useEffect, useSyncExternalStore } from "react";

type Choice = "system" | "light" | "dark";
const CHOICES: Choice[] = ["system", "light", "dark"];
const LABEL: Record<Choice, string> = { system: "Auto", light: "Light", dark: "Dark" };
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
          onClick={() => pick(c)}
          className={`h-9 rounded-full px-2 font-medium sm:min-w-14 sm:px-3 ${
            choice === c ? "bg-selected text-on-selected" : "text-masthead-muted hover:text-on-masthead"
          }`}
        >
          {LABEL[c]}
        </button>
      ))}
    </div>
  );
}
