import "../embed/litex-chess-elements.js";

const API_BASE = document.documentElement.dataset.chessApiBase || "/api";
const SOURCE_BASE = document.documentElement.dataset.chessSourceBase || "/textbook-source";
const BOOK_BASE = "/textbook/Chess";
const WORKBENCH_ROUTE = `${BOOK_BASE}/workbench`;
const main = document.getElementById("siteMain");
const chapterNav = document.getElementById("siteChapterNav");
const runtime = document.getElementById("siteRuntime");
let catalog = null;
let mounted = null;

function normalizePath(pathname) {
  const path = pathname.replace(/\/+$/, "") || BOOK_BASE;
  if (path === BOOK_BASE || path === `${BOOK_BASE}/index`) return `${BOOK_BASE}/position-state`;
  return path;
}

function routeFromLocation() {
  const path = normalizePath(window.location.pathname);
  if (path === WORKBENCH_ROUTE || path === "/playground/chess") return { kind: "workbench" };
  const prefix = `${BOOK_BASE}/`;
  return { kind: "chapter", slug: path.startsWith(prefix) ? decodeURIComponent(path.slice(prefix.length)) : "position-state" };
}

function link(path, label, options = {}) {
  const anchor = document.createElement("a");
  anchor.href = path;
  anchor.dataset.siteRoute = "";
  if (options.className) anchor.className = options.className;
  anchor.innerHTML = label;
  return anchor;
}

function renderNavigation(route) {
  if (!catalog) return;
  chapterNav.replaceChildren();
  let previousPart = null;
  for (const chapter of catalog.chapters || []) {
    if (chapter.part !== previousPart) {
      const heading = document.createElement("div");
      heading.className = "site-chapter-part";
      heading.textContent = chapter.part_title || chapter.part || "";
      chapterNav.appendChild(heading);
      previousPart = chapter.part;
    }
    const href = `${BOOK_BASE}/${encodeURIComponent(chapter.slug)}`;
    const anchor = link(href, `<span>${String(chapter.number).padStart(2, "0")}</span><b>${chapter.title}</b>`);
    anchor.classList.toggle("active", route.kind === "chapter" && route.slug === chapter.slug);
    chapterNav.appendChild(anchor);
  }
  const workbenchWrap = document.createElement("div");
  workbenchWrap.className = "site-workbench-nav";
  const workbench = link(WORKBENCH_ROUTE, "<span>↗</span><b>互动棋局工作台</b>");
  workbench.classList.toggle("active", route.kind === "workbench");
  workbenchWrap.appendChild(workbench);
  chapterNav.appendChild(workbenchWrap);
}

function mountRoute({ replace = false } = {}) {
  const route = routeFromLocation();
  renderNavigation(route);
  const query = window.location.search;
  if (mounted?.tagName === "LITEX-CHESS-TEXTBOOK" && route.kind === "chapter") {
    mounted.setAttribute("chapter", route.slug);
    return;
  }
  if (mounted?.tagName === "LITEX-CHESS-WORKBENCH" && route.kind === "workbench") {
    if (mounted.getAttribute("search") !== query) mounted.setAttribute("search", query);
    return;
  }
  mounted?.remove();
  mounted = route.kind === "workbench"
    ? document.createElement("litex-chess-workbench")
    : document.createElement("litex-chess-textbook");
  mounted.setAttribute("api-base", API_BASE);
  mounted.setAttribute("textbook-base", BOOK_BASE);
  if (route.kind === "workbench") {
    mounted.setAttribute("search", query);
  } else {
    mounted.setAttribute("source-base", SOURCE_BASE);
    mounted.setAttribute("chapter-base", BOOK_BASE);
    mounted.setAttribute("workbench-base", WORKBENCH_ROUTE);
    mounted.setAttribute("chapter", route.slug);
  }
  main.replaceChildren(mounted);
  if (!replace) main.focus({ preventScroll: true });
}

function navigate(url, { replace = false } = {}) {
  const target = new URL(url, window.location.href);
  if (replace) window.history.replaceState({}, "", target);
  else window.history.pushState({}, "", target);
  mountRoute({ replace });
  window.scrollTo({ top: 0, behavior: replace ? "auto" : "smooth" });
}

document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-site-route]");
  if (!anchor || anchor.target || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const target = new URL(anchor.href, window.location.href);
  if (target.origin !== window.location.origin) return;
  event.preventDefault();
  navigate(target.toString());
});

document.addEventListener("litex-chess-navigate", (event) => {
  const url = event.detail?.url;
  if (url) navigate(url);
});

window.addEventListener("popstate", () => mountRoute({ replace: true }));

async function initialize() {
  try {
    const [catalogResponse, healthResponse] = await Promise.all([
      fetch(`${SOURCE_BASE}/chapters.json`),
      fetch(`${API_BASE}/health`),
    ]);
    if (!catalogResponse.ok) throw new Error(`教材目录 HTTP ${catalogResponse.status}`);
    catalog = await catalogResponse.json();
    const health = healthResponse.ok ? await healthResponse.json() : null;
    runtime.classList.toggle("ready", Boolean(health?.gate?.ready));
    runtime.classList.toggle("failed", !health?.gate?.ready);
    runtime.querySelector("b").textContent = health?.gate?.ready
      ? `Litex 就绪 · ${health.version}`
      : "Litex 后端不可用";
    mountRoute({ replace: true });
  } catch (error) {
    runtime.classList.add("failed");
    runtime.querySelector("b").textContent = "扩展加载失败";
    main.innerHTML = `<section class="site-error"><strong>无法加载 Chess 教材扩展</strong><p>${String(error.message || error)}</p></section>`;
  }
}

initialize();
