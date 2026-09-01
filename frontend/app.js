"use strict";

window.addEventListener("DOMContentLoaded", () => {
  const root = document;
  window.LitexChessWorkbench.mount(root, {
    apiBase: "/api",
    textbookBase: "/textbook/Chess",
    search: window.location.search,
  });
});
