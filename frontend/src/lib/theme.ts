// Runs at the start of <body> before first paint (Next.js "preventing flash before hydration" guide), so no theme flash.
// Same rule as ThemeSwitch's apply(): a saved "light"/"dark" wins, otherwise the device setting.
export const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("theme");var d=c==="dark"||(c!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.setAttribute("data-theme",d?"dark":"light")}catch(e){}})()`;
