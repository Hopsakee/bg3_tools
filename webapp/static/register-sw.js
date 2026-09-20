// Registreert de service worker. Meer JavaScript heeft deze app niet nodig:
// filteren, sorteren en opslaan doet de server, zodat elke pagina ook zonder
// script werkt -- op e-ink is een volledige, rustige verversing prettiger dan
// een halve die je niet ziet gebeuren.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function (err) {
      console.warn("service worker niet geregistreerd:", err);
    });
  });
}
