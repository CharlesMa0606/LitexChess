/**
 * Framework-neutral Litex Chess textbook integration.
 *
 * The adapter creates native custom elements in the host route outlet. It does
 * not create an iframe or a second top-level application shell.
 */

const DEFAULTS = {
  entryUrl: "/extensions/chess/embed/litex-chess-elements.js",
  apiBase: "/api",
  sourceBase: "/textbook-source",
  routeBase: "/textbook/Chess",
};

let entryPromise;

async function ensureEntry(url) {
  if (!entryPromise) entryPromise = import(url);
  return entryPromise;
}

function normalizedRoute(route, routeBase) {
  const url = route instanceof URL ? route : new URL(String(route), globalThis.location?.origin || "http://localhost");
  const path = url.pathname.replace(/\/+$/, "");
  const base = routeBase.replace(/\/+$/, "");
  if (path === `${base}/workbench` || path === "/playground/chess") {
    return { kind: "workbench", search: url.search };
  }
  const prefix = `${base}/`;
  return {
    kind: "chapter",
    slug: path.startsWith(prefix) ? decodeURIComponent(path.slice(prefix.length)) : "position-state",
  };
}

export async function mountLitexChessRoute(outlet, route, options = {}) {
  if (!(outlet instanceof Element || outlet instanceof ShadowRoot)) {
    throw new TypeError("outlet must be an Element or ShadowRoot");
  }
  const config = { ...DEFAULTS, ...options };
  await ensureEntry(config.entryUrl);
  const parsed = normalizedRoute(route, config.routeBase);
  const element = document.createElement(parsed.kind === "workbench"
    ? "litex-chess-workbench"
    : "litex-chess-textbook");
  element.setAttribute("api-base", config.apiBase);
  element.setAttribute("textbook-base", config.routeBase);
  if (parsed.kind === "workbench") {
    element.setAttribute("search", parsed.search || "");
  } else {
    element.setAttribute("source-base", config.sourceBase);
    element.setAttribute("chapter-base", config.routeBase);
    element.setAttribute("workbench-base", `${config.routeBase}/workbench`);
    element.setAttribute("chapter", parsed.slug);
  }
  outlet.replaceChildren(element);
  return element;
}

/**
 * Register with a host that exposes route/textbook hooks. Every hook is
 * optional so the same file works with the private Litex site implementation
 * and with a small local harness.
 */
export async function registerLitexChess(host, options = {}) {
  const config = { ...DEFAULTS, ...options };
  const manifestUrl = options.manifestUrl || "/extensions/chess/integration/litex-site/manifest.json";
  const response = await fetch(manifestUrl);
  if (!response.ok) throw new Error(`Chess manifest HTTP ${response.status}`);
  const manifest = await response.json();
  await ensureEntry(config.entryUrl);

  host?.registerTextbook?.({
    ...manifest,
    render: (outlet, route) => mountLitexChessRoute(outlet, route, config),
  });

  for (const chapter of manifest.chapters || []) {
    host?.registerRoute?.(chapter.route, (context) =>
      mountLitexChessRoute(context.outlet, context.url || chapter.route, config));
  }
  host?.registerRoute?.(manifest.routes.workbench, (context) =>
    mountLitexChessRoute(context.outlet, context.url || manifest.routes.workbench, config));
  host?.registerRoute?.(manifest.routes.playground_alias, (context) =>
    mountLitexChessRoute(context.outlet, context.url || manifest.routes.workbench, config));

  return manifest;
}
