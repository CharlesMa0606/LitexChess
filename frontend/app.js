"use strict";

const PIECES = {
  1: "♙", 2: "♘", 3: "♗", 4: "♖", 5: "♕", 6: "♔",
  "-1": "♟", "-2": "♞", "-3": "♝", "-4": "♜", "-5": "♛", "-6": "♚",
};
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const state = {
  sessionId: null,
  tree: null,
  flipped: false,
  draggedFrom: null,
  busy: false,
  pgnMode: "import",
  formalMode: "agent",
  lessonContext: null,
  kernelSource: null,
  activeReceipt: null,
};

const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let payload = text;
  try { payload = text ? JSON.parse(text) : null; } catch (_) { /* plain text */ }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return payload;
}

function toast(message, error = false) {
  const el = byId("toast");
  el.textContent = message;
  el.className = `toast show${error ? " error" : ""}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = "toast"; }, 3600);
}

function formalLineClass(line) {
  const trimmed = line.trim();
  if (trimmed.startsWith("#")) return "comment";
  if (trimmed.startsWith("prop ") || trimmed.startsWith("have ") || trimmed.startsWith("struct ")) return "definition";
  if (trimmed.startsWith("by def ")) return "call";
  return "";
}

function receiptAgentSource(receipt) {
  if (!receipt) return "";
  if (receipt.agent_source) return receipt.agent_source;
  const source = receipt.formal_source || "";
  const match = source.match(/# \[agent-record:start\][\s\S]*?# \[agent-record:end\]/);
  return match ? `${match[0]}\n` : "";
}

function selectedFormalSource() {
  if (state.formalMode === "kernel") return state.kernelSource?.source || "";
  if (state.formalMode === "certificate") return state.activeReceipt?.formal_source || "";
  return receiptAgentSource(state.activeReceipt);
}

function renderFormalSource() {
  const viewer = byId("formalCodeViewer");
  const meta = byId("formalCodeMeta");
  const tabs = [
    ["agentSourceTab", "agent"],
    ["certificateSourceTab", "certificate"],
    ["kernelSourceTab", "kernel"],
  ];
  tabs.forEach(([id, mode]) => {
    const tab = byId(id);
    tab.classList.toggle("active", state.formalMode === mode);
    tab.setAttribute("aria-selected", String(state.formalMode === mode));
  });

  const source = selectedFormalSource();
  if (state.formalMode === "kernel") {
    meta.textContent = state.kernelSource
      ? `${state.kernelSource.project_path} · ${state.kernelSource.line_count} 行 · sha256 ${state.kernelSource.sha256}`
      : "正在读取固定规则内核…";
  } else if (state.activeReceipt) {
    const status = state.activeReceipt.outcome || "unclassified";
    const checkers = state.activeReceipt.checker_count ?? "—";
    const replies = state.activeReceipt.legal_reply_count ?? "—";
    const label = state.formalMode === "agent" ? "Agent 走法记录" : "完整 Litex 证书";
    meta.textContent = `${label} · ${state.activeReceipt.accepted ? "ACCEPT" : "REJECT"} · result=${status} · checkers=${checkers} · legal_replies=${replies} · sha256 ${state.activeReceipt.query_sha256}`;
  } else {
    meta.textContent = state.formalMode === "agent"
      ? "尚无本手记录；落子后将显示 move(...) 与 result(...)。"
      : "尚无本手证书；请落子或选择已有棋谱节点。";
  }

  viewer.innerHTML = "";
  if (!source) {
    const message = state.formalMode === "kernel"
      ? "固定规则内核尚未载入。"
      : state.formalMode === "agent"
        ? "根节点没有 move/result 记录；提交候选走法后将在这里显示同一 Litex 事务中的可读封面。"
        : "根节点没有落子证书；提交候选走法后将在这里显示实际发送给 Litex 的完整代码。";
    viewer.innerHTML = `<div class="formal-code-empty">${message}</div>`;
    return;
  }
  source.split(/\r?\n/).forEach((line, index) => {
    const row = document.createElement("div");
    row.className = `formal-code-line ${formalLineClass(line)}`.trim();
    const number = document.createElement("span");
    number.className = "formal-code-line-number";
    number.textContent = String(index + 1);
    const text = document.createElement("span");
    text.className = "formal-code-line-text";
    text.textContent = line || " ";
    row.append(number, text);
    viewer.appendChild(row);
  });
}

function setFormalMode(mode) {
  state.formalMode = ["agent", "certificate", "kernel"].includes(mode) ? mode : "agent";
  renderFormalSource();
}

async function loadKernelSource() {
  try {
    state.kernelSource = await api("/api/formal/source");
  } catch (error) {
    state.kernelSource = { source: "", project_path: "formal/chess_rules.lit", line_count: 0, sha256: `读取失败：${error.message}` };
  }
  renderFormalSource();
}

async function loadNodeReceipt(nodeId) {
  if (!state.sessionId || !nodeId) return;
  try {
    const payload = await api(`/api/sessions/${state.sessionId}/nodes/${encodeURIComponent(nodeId)}/receipt`);
    showReceipt(payload.receipt);
  } catch (error) {
    state.activeReceipt = null;
    renderFormalSource();
    toast(`无法读取节点回执：${error.message}`, true);
  }
}


function renderLessonContext(context) {
  state.lessonContext = context;
  const card = byId("lessonContext");
  if (!context) {
    card.hidden = true;
    byId("textbookLink").href = "/textbook";
    return;
  }
  card.hidden = false;
  byId("lessonContextTitle").textContent = context.title || context.lesson || context.lab || "教材局面";
  byId("lessonContextGoal").textContent = context.goal || "该局面从规则教材打开；工作台中的每一手仍由完整 Litex 门禁核验。";
  const returnUrl = context.returnUrl || "/textbook";
  byId("lessonContextReturn").href = returnUrl;
  byId("textbookLink").href = returnUrl;
}

async function resolveWorkbenchContext() {
  const params = new URLSearchParams(window.location.search);
  let fen = params.get("fen") || "";
  const context = {
    lesson: params.get("lesson") || "",
    lab: params.get("lab") || "",
    title: params.get("title") || "",
    goal: params.get("goal") || "",
    returnUrl: params.get("return") || "/textbook",
  };
  if (!fen && context.lab) {
    try {
      const lab = await api(`/api/textbook/board-labs/${encodeURIComponent(context.lab)}`);
      fen = lab.fen || "";
      context.title ||= lab.title || context.lab;
      context.goal ||= lab.instruction || "";
      context.returnUrl = params.get("return") || lab.textbook_url || "/textbook";
    } catch (error) {
      toast(`无法载入教材局面：${error.message}`, true);
    }
  }
  const active = Boolean(context.lesson || context.lab || params.get("title") || params.get("goal"));
  return { fen: fen || START_FEN, context: active ? context : null };
}

function setBusy(value) {
  state.busy = value;
  byId("board").classList.toggle("busy", value);
  document.querySelectorAll("button").forEach((button) => {
    if (!button.closest("dialog")) button.disabled = value;
  });
  if (!value) {
    const current = currentNode();
    byId("backButton").disabled = !current?.parent_id;
    byId("forwardButton").disabled = !current?.children?.length;
  }
}

function currentNode() {
  return state.tree?.nodes?.[state.tree.current_id] || null;
}

function orderedSquares() {
  const files = state.flipped ? [..."hgfedcba"] : [..."abcdefgh"];
  const ranks = state.flipped ? [..."12345678"] : [..."87654321"];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

function renderBoard() {
  const board = byId("board");
  board.innerHTML = "";
  const node = currentNode();
  if (!node) return;
  const pieces = node.position.pieces || {};
  const path = state.tree.path || [];
  const lastMove = path.length ? path[path.length - 1].move : null;

  for (const squareName of orderedSquares()) {
    const fileIndex = squareName.charCodeAt(0) - 96;
    const rank = Number(squareName[1]);
    const square = document.createElement("div");
    square.className = `square ${(fileIndex + rank) % 2 === 0 ? "dark" : "light"}`;
    square.dataset.square = squareName;
    if (lastMove && (lastMove.from === squareName || lastMove.to === squareName)) {
      square.classList.add("last");
    }
    const visibleFileEdge = state.flipped ? fileIndex === 8 : fileIndex === 1;
    const visibleRankEdge = state.flipped ? rank === 8 : rank === 1;
    if (visibleFileEdge) {
      const label = document.createElement("span");
      label.className = "coord-rank";
      label.textContent = rank;
      square.appendChild(label);
    }
    if (visibleRankEdge) {
      const label = document.createElement("span");
      label.className = "coord-file";
      label.textContent = squareName[0];
      square.appendChild(label);
    }
    const code = pieces[squareName];
    if (code) {
      const piece = document.createElement("div");
      piece.className = `piece ${Number(code) > 0 ? "white" : "black"}`;
      piece.textContent = PIECES[code];
      piece.draggable = true;
      piece.dataset.square = squareName;
      piece.addEventListener("dragstart", onDragStart);
      piece.addEventListener("dragend", () => { state.draggedFrom = null; });
      square.appendChild(piece);
    }
    square.addEventListener("dragover", (event) => {
      event.preventDefault();
      square.classList.add("drag-over");
    });
    square.addEventListener("dragleave", () => square.classList.remove("drag-over"));
    square.addEventListener("drop", onDrop);
    board.appendChild(square);
  }
  byId("turnLabel").textContent = node.position.turn === "white" ? "白方行棋" : "黑方行棋";
  byId("nodeLabel").textContent = state.tree.current_id;
  byId("fenInput").value = node.position.fen;
}

function onDragStart(event) {
  state.draggedFrom = event.currentTarget.dataset.square;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", state.draggedFrom);
}

async function onDrop(event) {
  event.preventDefault();
  event.currentTarget.classList.remove("drag-over");
  if (state.busy || !state.sessionId) return;
  const from = state.draggedFrom || event.dataTransfer.getData("text/plain");
  const to = event.currentTarget.dataset.square;
  if (!from || !to || from === to) return;
  const node = currentNode();
  const code = Number(node.position.pieces[from] || 0);
  let promotion = null;
  if (Math.abs(code) === 1 && (to[1] === "1" || to[1] === "8")) {
    const answer = window.prompt("升变为 q / r / b / n", "q");
    if (answer === null) return;
    promotion = answer.trim().toLowerCase();
    if (!["q", "r", "b", "n"].includes(promotion)) {
      toast("升变代码必须是 q、r、b 或 n", true);
      return;
    }
  }
  await submitMove(from, to, promotion);
}

async function submitMove(from, to, promotion) {
  setBusy(true);
  try {
    const payload = await api(`/api/sessions/${state.sessionId}/move`, {
      method: "POST",
      body: JSON.stringify({
        from,
        to,
        promotion,
        parent_id: state.tree.current_id,
      }),
    });
    state.tree = payload.tree;
    showReceipt(payload.receipt);
    renderAll();
    if (!payload.accepted) {
      toast("Litex 未能证明该走法合法，棋盘保持不变。", true);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function showReceipt(receipt) {
  const badge = byId("receiptBadge");
  const summary = byId("receiptSummary");
  const output = byId("receiptOutput");
  if (!receipt) {
    badge.className = "receipt-badge neutral";
    badge.textContent = "尚未提交";
    summary.textContent = "根节点没有落子证书。选择已有走法或提交新候选后，可在下方查看实际 Litex 查询。";
    output.textContent = "";
    state.activeReceipt = null;
    renderFormalSource();
    return;
  }
  state.activeReceipt = receipt;
  badge.className = `receipt-badge ${receipt.accepted ? "success" : "failure"}`;
  badge.textContent = receipt.accepted ? "已证明 / ACCEPT" : "未证明 / REJECT";
  summary.textContent = `${receipt.reason}；引擎 ${receipt.engine}；耗时 ${receipt.elapsed_ms} ms；查询摘要 ${receipt.query_sha256}.`;
  output.textContent = JSON.stringify(receipt, null, 2);
  byId("receiptDetails").open = !receipt.accepted;
  renderFormalSource();
}

function createMoveButton(nodeId, extraClass = "") {
  const node = state.tree.nodes[nodeId];
  const button = document.createElement("button");
  button.type = "button";
  button.className = `notation-move${extraClass ? ` ${extraClass}` : ""}`;
  button.dataset.nodeId = nodeId;
  button.textContent = node.san || node.move?.uci || "?";
  button.title = node.position.fen;
  if (nodeId === state.tree.current_id) button.classList.add("current");
  button.addEventListener("click", () => gotoNode(nodeId));
  return button;
}

function appendNodeAnnotations(container, node) {
  for (const nag of node.nags || []) {
    const mark = document.createElement("span");
    mark.className = "notation-nag";
    mark.textContent = nag;
    container.appendChild(mark);
  }
  if (node.comment) {
    const comment = document.createElement("span");
    comment.className = "notation-comment";
    comment.textContent = `{${node.comment}}`;
    container.appendChild(comment);
  }
}

function appendVariationToken(stream, token) {
  if (token.kind === "move") {
    stream.appendChild(createMoveButton(token.nodeId, "variation-move"));
    return;
  }
  const element = document.createElement("span");
  const classMap = {
    prefix: "variation-prefix",
    nag: "notation-nag",
    comment: "notation-comment",
    paren: `variation-paren${token.topLevel ? " top-level" : ""}`,
  };
  element.className = classMap[token.kind] || "variation-token";
  element.textContent = token.text;
  stream.appendChild(element);
}

function createVariationBlock(blockModel) {
  const block = document.createElement("div");
  block.className = "notation-variation-row";

  const rail = document.createElement("span");
  rail.className = "variation-rail";
  rail.setAttribute("aria-hidden", "true");
  block.appendChild(rail);

  const stream = document.createElement("div");
  stream.className = "variation-stream";
  for (const token of blockModel.tokens || []) appendVariationToken(stream, token);
  block.appendChild(stream);
  return block;
}

function appendNotationRow(container, row) {
  const line = document.createElement("div");
  line.className = "notation-row";

  const number = document.createElement("span");
  number.className = "notation-number";
  number.textContent = `${row.fullmove}.`;
  line.appendChild(number);

  const whiteCell = document.createElement("div");
  whiteCell.className = "notation-cell white-cell";
  if (row.whiteId) {
    whiteCell.appendChild(createMoveButton(row.whiteId));
    appendNodeAnnotations(whiteCell, state.tree.nodes[row.whiteId]);
  } else if (row.leadingEllipsis) {
    const ellipsis = document.createElement("span");
    ellipsis.className = "notation-ellipsis";
    ellipsis.textContent = "...";
    whiteCell.appendChild(ellipsis);
  }
  line.appendChild(whiteCell);

  const blackCell = document.createElement("div");
  blackCell.className = "notation-cell black-cell";
  if (row.blackId) {
    blackCell.appendChild(createMoveButton(row.blackId));
    appendNodeAnnotations(blackCell, state.tree.nodes[row.blackId]);
  } else if (row.trailingEllipsis) {
    const ellipsis = document.createElement("span");
    ellipsis.className = "notation-ellipsis";
    ellipsis.textContent = "...";
    blackCell.appendChild(ellipsis);
  }
  line.appendChild(blackCell);
  container.appendChild(line);
}

function renderTree() {
  const container = byId("moveTree");
  container.innerHTML = "";
  if (!state.tree) {
    container.innerHTML = '<div class="empty-tree">尚未建立棋局</div>';
    return;
  }

  const titlebar = document.createElement("div");
  titlebar.className = "notation-titlebar";
  const matchup = document.createElement("div");
  matchup.className = "notation-matchup";
  const whiteName = state.tree.headers?.White || "White";
  const blackName = state.tree.headers?.Black || "Black";
  const result = state.tree.headers?.Result || "*";
  matchup.textContent = `${whiteName} — ${blackName} ${result}`;
  titlebar.appendChild(matchup);

  const rootButton = document.createElement("button");
  rootButton.type = "button";
  rootButton.className = "notation-root-button";
  rootButton.textContent = "起始局面";
  if (state.tree.current_id === state.tree.root_id) rootButton.classList.add("current");
  rootButton.addEventListener("click", () => gotoNode(state.tree.root_id));
  titlebar.appendChild(rootButton);
  container.appendChild(titlebar);

  const columnHead = document.createElement("div");
  columnHead.className = "notation-column-head";
  columnHead.innerHTML = "<span></span><span>白方</span><span>黑方</span>";
  container.appendChild(columnHead);

  let blocks;
  try {
    blocks = window.LitexChessNotation.buildNotationBlocks(state.tree);
  } catch (error) {
    const failure = document.createElement("div");
    failure.className = "empty-tree notation-error";
    failure.textContent = `棋谱结构无法呈现：${error.message}`;
    container.appendChild(failure);
    return;
  }

  let moveCount = 0;
  for (const block of blocks) {
    if (block.type === "variation") {
      container.appendChild(createVariationBlock(block));
    } else {
      appendNotationRow(container, block);
      moveCount += Number(Boolean(block.whiteId)) + Number(Boolean(block.blackId));
    }
  }

  if (!moveCount) {
    const empty = document.createElement("div");
    empty.className = "empty-tree";
    empty.textContent = "从棋盘落子，或导入带主线与括号变例的 PGN。";
    container.appendChild(empty);
  }

  const current = container.querySelector(".notation-move.current");
  if (current) current.scrollIntoView({ block: "nearest", inline: "nearest" });
}

async function gotoNode(nodeId) {
  if (!state.sessionId || state.busy) return;
  setBusy(true);
  try {
    const payload = await api(`/api/sessions/${state.sessionId}/goto`, {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId }),
    });
    state.tree = payload.tree;
    renderAll();
    await loadNodeReceipt(nodeId);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderAll() {
  renderBoard();
  renderTree();
  const current = currentNode();
  byId("backButton").disabled = state.busy || !current?.parent_id;
  byId("forwardButton").disabled = state.busy || !current?.children?.length;
}

async function createSession(fen = START_FEN) {
  setBusy(true);
  try {
    const payload = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        fen,
        validate_root: byId("validateRootCheckbox").checked,
      }),
    });
    state.sessionId = payload.session_id;
    state.tree = payload.tree;
    showReceipt(payload.root_receipt);
    renderAll();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function checkHealth() {
  const pill = byId("enginePill");
  try {
    const payload = await api("/api/health");
    const ready = Boolean(payload.gate?.ready);
    pill.classList.toggle("ready", ready);
    pill.classList.toggle("failed", !ready);
    byId("engineText").textContent = ready
      ? `Litex 就绪 · ${payload.gate.engine}`
      : "Litex 不可用 · 所有走法将拒绝";
  } catch (error) {
    pill.classList.add("failed");
    byId("engineText").textContent = "后端连接失败";
  }
}

function openPgnDialog(mode) {
  state.pgnMode = mode;
  const dialog = byId("pgnDialog");
  const textarea = byId("pgnTextarea");
  byId("pgnDialogTitle").textContent = mode === "import" ? "导入 PGN" : "导出 PGN";
  byId("pgnConfirmButton").textContent = mode === "import" ? "逐步验证并导入" : "复制到剪贴板";
  byId("pgnHint").textContent = mode === "import"
    ? "主线与括号变例都会逐步提交 Litex。"
    : "导出的每条边都来自此前已接受的 Litex 回执。";
  textarea.readOnly = mode === "export";
  textarea.value = "";
  dialog.showModal();
  if (mode === "export") loadExport();
}

async function loadExport() {
  try {
    const response = await fetch(`/api/sessions/${state.sessionId}/export-pgn`);
    if (!response.ok) throw new Error(await response.text());
    byId("pgnTextarea").value = await response.text();
  } catch (error) {
    toast(error.message, true);
  }
}

async function confirmPgn(event) {
  event.preventDefault();
  if (state.pgnMode === "export") {
    await navigator.clipboard.writeText(byId("pgnTextarea").value);
    toast("PGN 已复制到剪贴板");
    byId("pgnDialog").close();
    return;
  }
  const text = byId("pgnTextarea").value;
  if (!text.trim()) {
    toast("请粘贴 PGN", true);
    return;
  }
  byId("pgnDialog").close();
  setBusy(true);
  try {
    const payload = await api("/api/import-pgn", {
      method: "POST",
      body: JSON.stringify({
        pgn: text,
        validate_root: byId("validateRootCheckbox").checked,
      }),
    });
    state.sessionId = payload.session_id;
    state.tree = payload.tree;
    renderAll();
    await loadNodeReceipt(state.tree.current_id);
    toast("PGN 主线与变例已通过逐步 Litex 门禁并导入");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function wireEvents() {
  byId("newGameButton").addEventListener("click", () => { renderLessonContext(null); createSession(START_FEN); });
  byId("flipButton").addEventListener("click", () => { state.flipped = !state.flipped; renderBoard(); });
  byId("loadFenButton").addEventListener("click", () => createSession(byId("fenInput").value));
  byId("backButton").addEventListener("click", () => {
    const parent = currentNode()?.parent_id;
    if (parent) gotoNode(parent);
  });
  byId("forwardButton").addEventListener("click", () => {
    const child = currentNode()?.children?.[0];
    if (child) gotoNode(child);
  });
  byId("importButton").addEventListener("click", () => openPgnDialog("import"));
  byId("exportButton").addEventListener("click", () => openPgnDialog("export"));
  byId("pgnConfirmButton").addEventListener("click", confirmPgn);
  document.querySelectorAll(".formal-code-tab").forEach((button) => {
    button.addEventListener("click", () => setFormalMode(button.dataset.sourceMode));
  });
  byId("copyFormalButton").addEventListener("click", async () => {
    const source = selectedFormalSource();
    if (!source) {
      toast("当前没有可复制的 Litex 源码", true);
      return;
    }
    try {
      await navigator.clipboard.writeText(source);
      toast("Litex 源码已复制");
    } catch (_) {
      toast("浏览器未允许访问剪贴板", true);
    }
  });
}

async function boot() {
  wireEvents();
  renderFormalSource();
  await loadKernelSource();
  await checkHealth();
  const initial = await resolveWorkbenchContext();
  renderLessonContext(initial.context);
  await createSession(initial.fen);
}

boot();
