// Apply the saved theme before first paint so the page doesn't flash.
// A separate file rather than an inline script, so the page also works under a
// Content-Security-Policy that only allows scripts from its own origin.
try { var t = localStorage.getItem("bg3-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
