"use strict";

window.addEventListener("DOMContentLoaded", () => {
  window.LitexChessTextbook.mount(document, {
    apiBase: "/api",
    sourceBase: "/textbook-source",
    chapterBase: "/textbook/Chess",
    workbenchBase: "/textbook/Chess/workbench",
    manageHash: true,
    manageDocumentTitle: true,
  });
});
