const moduleBase = new URL("./", import.meta.url);
const assetBase = new URL("../", import.meta.url);
const textCache = new Map();
const moduleCache = new Map();

function asset(path) {
  return new URL(path, assetBase).toString();
}

function embedded(path) {
  return new URL(path, moduleBase).toString();
}

async function loadText(url) {
  const key = String(url);
  if (!textCache.has(key)) {
    textCache.set(key, fetch(key).then((response) => {
      if (!response.ok) throw new Error(`Unable to load ${key}: HTTP ${response.status}`);
      return response.text();
    }));
  }
  return textCache.get(key);
}

async function loadModule(url) {
  const key = String(url);
  if (!moduleCache.has(key)) moduleCache.set(key, import(key));
  return moduleCache.get(key);
}

function failureMarkup(error) {
  const message = String(error?.stack || error?.message || error || "Unknown error");
  return `<section class="litex-chess-embed-error" role="alert"><strong>国际象棋模块加载失败</strong><pre>${message.replaceAll("&", "&amp;").replaceAll("<", "&lt;")}</pre></section>`;
}

class LitexChessElement extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._controller = null;
    this._renderToken = 0;
  }

  disconnectedCallback() {
    this._controller?.destroy?.();
    this._controller = null;
  }

  stringAttribute(name, fallback) {
    const value = this.getAttribute(name);
    return value == null || value === "" ? fallback : value;
  }

  emitNavigate(detail) {
    this.dispatchEvent(new CustomEvent("litex-chess-navigate", {
      bubbles: true,
      composed: true,
      detail,
    }));
  }

  async install(fragmentPath, cssPath) {
    const token = ++this._renderToken;
    const [fragment, css] = await Promise.all([
      loadText(embedded(fragmentPath)),
      loadText(embedded(cssPath)),
    ]);
    if (token !== this._renderToken) return false;
    this.shadowRoot.innerHTML = `<style>${css}</style>${fragment}`;
    return true;
  }
}

class LitexChessTextbookElement extends LitexChessElement {
  static observedAttributes = ["chapter"];

  connectedCallback() {
    if (!this._controller) this.render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (name === "chapter" && oldValue !== newValue && this._controller) {
      this._controller.selectChapterBySlug(newValue, false);
    }
  }

  async render() {
    try {
      const installed = await this.install("fragments/textbook.html", "textbook.css");
      if (!installed) return;
      await loadModule(asset("controllers/textbook.js"));
      const chapterBase = this.stringAttribute("chapter-base", "/textbook/Chess");
      const workbenchBase = this.stringAttribute("workbench-base", `${chapterBase}/workbench`);
      const workbenchLink = this.shadowRoot.querySelector("[data-litex-chess-route='workbench']");
      if (workbenchLink) workbenchLink.href = workbenchBase;
      this._controller = globalThis.LitexChessTextbook.mount(this.shadowRoot, {
        apiBase: this.stringAttribute("api-base", "/api"),
        sourceBase: this.stringAttribute("source-base", "/textbook-source"),
        chapterBase,
        workbenchBase,
        initialChapter: this.stringAttribute("chapter", "position-state"),
        manageHash: false,
        manageScroll: false,
        manageDocumentTitle: false,
        onChapterChange: (chapter, meta) => this.emitNavigate({
          kind: "chapter",
          chapter,
          url: meta.url,
        }),
      });
      await this._controller.ready;
      this.dispatchEvent(new CustomEvent("litex-chess-ready", {
        bubbles: true,
        composed: true,
        detail: {
          kind: "textbook",
          catalog: this._controller.state.catalog,
          chapter: this._controller.currentChapter(),
        },
      }));
    } catch (error) {
      this.shadowRoot.innerHTML = failureMarkup(error);
    }
  }
}

class LitexChessWorkbenchElement extends LitexChessElement {
  static observedAttributes = ["search"];

  connectedCallback() {
    if (!this._controller) this.render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (name !== "search" || oldValue === newValue || !this.isConnected || !this._controller) return;
    this._controller.destroy?.();
    this._controller = null;
    this.render();
  }

  async render() {
    try {
      const installed = await this.install("fragments/workbench.html", "workbench.css");
      if (!installed) return;
      await loadModule(asset("notation.js"));
      await loadModule(asset("controllers/workbench.js"));
      const textbookBase = this.stringAttribute("textbook-base", "/textbook/Chess");
      this._controller = globalThis.LitexChessWorkbench.mount(this.shadowRoot, {
        apiBase: this.stringAttribute("api-base", "/api"),
        textbookBase,
        search: this.stringAttribute("search", globalThis.location?.search || ""),
        notation: globalThis.LitexChessNotation,
      });
      await this._controller.ready;
      this.dispatchEvent(new CustomEvent("litex-chess-ready", {
        bubbles: true,
        composed: true,
        detail: { kind: "workbench" },
      }));
    } catch (error) {
      this.shadowRoot.innerHTML = failureMarkup(error);
    }
  }
}

if (!customElements.get("litex-chess-textbook")) {
  customElements.define("litex-chess-textbook", LitexChessTextbookElement);
}
if (!customElements.get("litex-chess-workbench")) {
  customElements.define("litex-chess-workbench", LitexChessWorkbenchElement);
}

export { LitexChessTextbookElement, LitexChessWorkbenchElement };
