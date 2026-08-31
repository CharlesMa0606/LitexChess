"use strict";

const state = {
  catalog: null,
  source: "",
  status: null,
  chapterIndex: 0,
  runAllResult: null,
  exampleResults: new Map(),
  boardResults: new Map(),
  statusResults: new Map(),
  historyResults: new Map(),
  endgameCatalog: [],
  endgameSession: null,
  endgameSelectedSource: null,
  endgameBusy: false,
  busy: false,
};

const byId = (id) => document.getElementById(id);

const PIECE_GLYPHS = {
  1: "♙", 2: "♘", 3: "♗", 4: "♖", 5: "♕", 6: "♔",
  "-1": "♟", "-2": "♞", "-3": "♝", "-4": "♜", "-5": "♛", "-6": "♚",
};

const PIECE_NAMES = {
  0: "空格",
  1: "白兵", 2: "白马", 3: "白象", 4: "白车", 5: "白后", 6: "白王",
  "-1": "黑兵", "-2": "黑马", "-3": "黑象", "-4": "黑车", "-5": "黑后", "-6": "黑王",
};

const FEN_PIECES = {
  P: 1, N: 2, B: 3, R: 4, Q: 5, K: 6,
  p: -1, n: -2, b: -3, r: -4, q: -5, k: -6,
};

const GROUP_NAMES = {
  precondition: "前置结构",
  shape: "走子形状",
  safety: "王安全",
  board: "稀疏棋盘后继",
  metadata: "FEN 元数据",
  total: "总接受合同",
  other: "其他",
};

const STATUS_LABELS = {
  ongoing: "继续进行",
  check: "将军，但仍有合法应对",
  checkmate: "将死",
  stalemate: "逼和",
};

const STATUS_CLASSES = {
  ongoing: "ongoing",
  check: "check",
  checkmate: "checkmate",
  stalemate: "stalemate",
};

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" ? payload.detail : payload;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return payload;
}

function toast(message, error = false) {
  const element = byId("bookToast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 3000);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function currentChapter() {
  return state.catalog?.chapters?.[state.chapterIndex] || null;
}

function findCurrentLab(labId) {
  return (currentChapter()?.board_labs || []).find((lab) => lab.id === labId) || null;
}

function parseSourceRanges() {
  const lines = state.source.split(/\r?\n/);
  const starts = new Map();
  const ranges = {};
  lines.forEach((line, index) => {
    const match = line.trim().match(/^# \[chapter:([a-z0-9-]+):(start|end)\]$/);
    if (!match) return;
    const [, slug, kind] = match;
    if (kind === "start") starts.set(slug, index + 2);
    else if (starts.has(slug)) {
      ranges[slug] = { start_line: starts.get(slug), end_line: index };
      starts.delete(slug);
    }
  });
  return ranges;
}

function parseFen(fen) {
  const [placement, active, castling, ep, halfmove, fullmove] = String(fen).trim().split(/\s+/);
  const pieces = {};
  const rankTokens = placement.split("/");
  rankTokens.forEach((token, index) => {
    const rank = 8 - index;
    let file = 1;
    for (const char of token) {
      if (/\d/.test(char)) {
        file += Number(char);
      } else {
        const square = `${String.fromCharCode(96 + file)}${rank}`;
        pieces[square] = FEN_PIECES[char];
        file += 1;
      }
    }
  });
  return {
    fen,
    pieces,
    turn: active === "w" ? "white" : "black",
    castling,
    ep: ep === "-" ? null : ep,
    halfmove: Number(halfmove),
    fullmove: Number(fullmove),
  };
}

function normalizePosition(positionOrFen) {
  return typeof positionOrFen === "string" ? parseFen(positionOrFen) : positionOrFen;
}

function fenFieldRows(positionOrFen) {
  const position = normalizePosition(positionOrFen);
  return [
    ["行棋方", position.turn === "white" ? "白方" : "黑方"],
    ["易位权", position.castling || "-"],
    ["过路兵格", position.ep || "-"],
    ["半回合", position.halfmove],
    ["完整回合", position.fullmove],
  ];
}

function updateRuntime(status) {
  const pill = byId("runtimePill");
  const ready = Boolean(status?.ready && status?.interactive_ready);
  pill.classList.toggle("ready", ready);
  pill.classList.toggle("failed", !ready);
  byId("runtimeText").textContent = ready
    ? `Litex 与局面实验就绪 · ${status.binary?.split(/[\\/]/).pop() || "local"}`
    : status?.ready ? "Litex 就绪，局面门禁不可用" : "Litex 不可用";

  const mirror = status?.mirror;
  const mirrorEl = byId("mirrorStatus");
  mirrorEl.textContent = mirror?.in_sync
    ? `${mirror.core_code_lines} 行定义一致`
    : "定义不一致";
  mirrorEl.className = mirror?.in_sync ? "pass" : "fail";

  const markerEl = byId("markerStatus");
  markerEl.textContent = status?.markers_match_catalog
    ? `${status.source_module_count ?? status.chapter_count} 个源码模块一致`
    : "目录与标记不一致";
  markerEl.className = status?.markers_match_catalog ? "pass" : "fail";

  const labEl = byId("labStatus");
  labEl.textContent = `${status?.board_lab_count ?? 0} 个走法局面 · ${status?.status_lab_count ?? 0} 个状态 · ${status?.history_lab_count ?? 0} 个历史实验`;
  labEl.className = status?.interactive_ready ? "pass" : "fail";
}

function renderSidebar() {
  const nav = byId("chapterNav");
  nav.innerHTML = "";
  let previousPart = null;
  state.catalog.chapters.forEach((chapter, index) => {
    if (chapter.part !== previousPart) {
      const heading = document.createElement("div");
      heading.className = "chapter-part-heading";
      heading.textContent = chapter.part_title || chapter.part || "";
      nav.appendChild(heading);
      previousPart = chapter.part;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chapter-link";
    button.dataset.slug = chapter.slug;
    button.innerHTML = `<span class="chapter-index">${String(chapter.number).padStart(2, "0")}</span><span class="chapter-name">${escapeHtml(chapter.title)}</span>`;
    button.addEventListener("click", () => selectChapter(index));
    nav.appendChild(button);
  });
}

function lineClass(line) {
  const trimmed = line.trim();
  if (trimmed.startsWith("#")) return "comment";
  if (trimmed.startsWith("prop ") || trimmed.startsWith("have ")) return "definition";
  if (trimmed.startsWith("by def ")) return "example";
  return "";
}

function renderSource(chapter) {
  const ranges = state.status?.chapter_ranges || parseSourceRanges();
  const refs = chapter.source_refs?.length ? chapter.source_refs : [chapter.slug];
  const editor = byId("sourceEditor");
  editor.innerHTML = "";
  const missing = refs.filter((ref) => !ranges[ref]);
  if (missing.length) {
    editor.innerHTML = `<div class="source-result-empty"><p>未找到源码模块：${escapeHtml(missing.join(", "))}</p></div>`;
    byId("sourceRange").textContent = "Source lines —";
    return;
  }
  const lines = state.source.split(/\r?\n/);
  byId("sourceRange").textContent = refs.map((ref) => `${ref}: ${ranges[ref].start_line}–${ranges[ref].end_line}`).join(" · ");
  refs.forEach((ref, refIndex) => {
    const range = ranges[ref];
    const header = document.createElement("div");
    header.className = "source-module-header";
    const title = state.catalog.source_modules?.find((item) => item.slug === ref)?.title || ref;
    header.innerHTML = `<strong>${escapeHtml(title)}</strong><code>${escapeHtml(ref)}</code><span>lines ${range.start_line}–${range.end_line}</span>`;
    editor.appendChild(header);
    for (let lineNumber = range.start_line; lineNumber <= range.end_line; lineNumber += 1) {
      const raw = lines[lineNumber - 1] ?? "";
      const row = document.createElement("div");
      row.className = `source-line ${lineClass(raw)}`.trim();
      row.innerHTML = `<span class="source-line-number">${lineNumber}</span><span class="source-line-code">${escapeHtml(raw) || " "}</span>`;
      editor.appendChild(row);
    }
    if (refIndex < refs.length - 1) {
      const divider = document.createElement("div");
      divider.className = "source-module-divider";
      editor.appendChild(divider);
    }
  });
}

function renderGoals(chapter) {
  const grid = byId("chapterGoals");
  grid.innerHTML = "";
  (chapter.goals || []).forEach((goal, index) => {
    const card = document.createElement("div");
    card.className = "goal-card";
    card.dataset.index = String(index + 1);
    card.textContent = goal;
    grid.appendChild(card);
  });
}

function renderNarrative(chapter) {
  const container = byId("lessonNarrative");
  const lessons = chapter.lesson || [];
  byId("lessonNarrativeSection").hidden = lessons.length === 0;
  container.innerHTML = lessons.map((lesson, index) => `
    <article class="lesson-block">
      <div class="lesson-number">${String(index + 1).padStart(2, "0")}</div>
      <div class="lesson-copy">
        <h3>${escapeHtml(lesson.title)}</h3>
        ${(lesson.paragraphs || []).map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
        ${(lesson.points || []).length ? `<ul>${lesson.points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : ""}
      </div>
    </article>
  `).join("");
}

function renderStateFields(chapter) {
  const fields = chapter.state_fields || [];
  const section = byId("stateFieldsSection");
  section.hidden = fields.length === 0;
  byId("stateFieldGrid").innerHTML = fields.map((item) => `
    <article class="state-field-card">
      <div class="state-field-key">${escapeHtml(item.field)}</div>
      <h3>${escapeHtml(item.name)}</h3>
      <code>${escapeHtml(item.example)}</code>
      <p>${escapeHtml(item.meaning)}</p>
      <small>内部：${escapeHtml(item.stored_as)}</small>
    </article>
  `).join("");
}

function renderWorkflow(chapter) {
  const steps = chapter.workflow || [];
  const section = byId("workflowSection");
  section.hidden = steps.length === 0;
  byId("workflowTrack").innerHTML = steps.map((step, index) => `
    <article class="workflow-card">
      <div class="workflow-index">${index + 1}</div>
      <span>${escapeHtml(step.owner)}</span>
      <h3>${escapeHtml(step.title)}</h3>
      <p>${escapeHtml(step.detail)}</p>
    </article>
  `).join("");
}

function squareColor(fileIndex, rank) {
  return (fileIndex + rank) % 2 === 0 ? "dark" : "light";
}

function boardMarkup(positionOrFen, options = {}) {
  const position = normalizePosition(positionOrFen);
  const orientation = options.orientation === "black" ? "black" : "white";
  const files = orientation === "white"
    ? ["a", "b", "c", "d", "e", "f", "g", "h"]
    : ["h", "g", "f", "e", "d", "c", "b", "a"];
  const ranks = orientation === "white"
    ? [8, 7, 6, 5, 4, 3, 2, 1]
    : [1, 2, 3, 4, 5, 6, 7, 8];
  const marks = new Map((options.marks || []).map((mark) => [mark.square, mark]));
  const targetMoves = options.targetMoves || new Map();
  const changed = new Set(options.changedSquares || []);
  const source = options.activeSquare || "";
  const staticBoard = Boolean(options.staticBoard);
  const compact = Boolean(options.compact);
  const squares = [];

  ranks.forEach((rank) => {
    files.forEach((file) => {
      const square = `${file}${rank}`;
      const fileIndex = file.charCodeAt(0) - 96;
      const piece = position.pieces?.[square] || 0;
      const mark = marks.get(square);
      const candidates = targetMoves.get(square) || [];
      const classes = ["mini-square", squareColor(fileIndex, rank)];
      if (square === source) classes.push("locked-source");
      if (mark?.kind) classes.push(`mark-${mark.kind}`);
      if (candidates.length) classes.push("candidate-square");
      if (changed.has(square)) classes.push("changed-square");
      const tag = !staticBoard && candidates.length ? "button" : "div";
      const attributes = tag === "button"
        ? `type="button" data-lab-id="${escapeHtml(options.labId)}" data-target-square="${square}"`
        : "";
      const titleParts = [square, PIECE_NAMES[piece] || "空格"];
      if (mark?.label) titleParts.push(mark.label);
      if (candidates.length) titleParts.push(candidates.map((move) => move.label).join(" / "));
      squares.push(`
        <${tag} class="${classes.join(" ")}" ${attributes} title="${escapeHtml(titleParts.join(" · "))}" aria-label="${escapeHtml(titleParts.join("，"))}">
          <span class="piece-glyph">${PIECE_GLYPHS[piece] || ""}</span>
          ${mark?.label ? `<span class="square-mark-label">${escapeHtml(mark.label)}</span>` : ""}
          ${file === files[0] ? `<span class="rank-label">${rank}</span>` : ""}
          ${rank === ranks[ranks.length - 1] ? `<span class="file-label">${file}</span>` : ""}
        </${tag}>`);
    });
  });
  return `<div class="mini-board ${compact ? "compact" : ""}" role="grid" aria-label="国际象棋迷你棋盘">${squares.join("")}</div>`;
}

function stateChips(positionOrFen) {
  return `<div class="position-state-strip">${fenFieldRows(positionOrFen).map(([label, value]) => `
    <span><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong></span>
  `).join("")}</div>`;
}

function markerLegend(lab) {
  const seen = new Set();
  const rows = [];
  for (const mark of lab.marks || []) {
    const key = `${mark.kind}:${mark.label}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(`<span class="legend-item"><i class="legend-swatch mark-${escapeHtml(mark.kind)}"></i>${escapeHtml(mark.label)}</span>`);
  }
  return rows.length ? `<div class="board-legend">${rows.join("")}</div>` : "";
}

function targetMoveMap(lab) {
  const map = new Map();
  for (const move of lab.moves || []) {
    const target = move.uci.slice(2, 4);
    if (!map.has(target)) map.set(target, []);
    map.get(target).push(move);
  }
  return map;
}

function pieceValueMarkup(value) {
  const glyph = PIECE_GLYPHS[value] || "·";
  return `<span class="piece-value"><b>${glyph}</b><code>${escapeHtml(value)}</code></span>`;
}

function renderPipeline(trace) {
  return `<div class="trace-pipeline">${(trace.pipeline || []).map((step) => `
    <article class="trace-stage">
      <span class="trace-stage-index">${step.index}</span>
      <small>${escapeHtml(step.owner)}</small>
      <h5>${escapeHtml(step.title)}</h5>
      <p>${escapeHtml(step.detail)}</p>
      ${step.outcome ? `<strong>${escapeHtml(step.outcome)}</strong>` : ""}
    </article>
  `).join("")}</div>`;
}

function renderFenComparison(trace) {
  const labels = {
    placement: "棋子摆放",
    active: "行棋方",
    castling: "易位权",
    ep: "过路兵格",
    halfmove: "半回合",
    fullmove: "完整回合",
  };
  const keys = ["placement", "active", "castling", "ep", "halfmove", "fullmove"];
  return `
    <p class="trace-explanation">${escapeHtml(trace.fen.explanation)}</p>
    <div class="trace-table-wrap"><table class="trace-table fen-table">
      <thead><tr><th>字段</th><th>走前</th><th>机械候选</th><th>独立期望</th></tr></thead>
      <tbody>${keys.map((key) => {
        const before = trace.fen.before[key];
        const candidate = trace.fen.candidate_after[key];
        const expected = trace.fen.expected_after[key];
        const match = candidate === expected;
        return `<tr class="${match ? "match" : "mismatch"}"><th>${labels[key]}</th><td><code>${escapeHtml(before)}</code></td><td><code>${escapeHtml(candidate)}</code></td><td><code>${escapeHtml(expected)}</code>${match ? " ✓" : " ✕"}</td></tr>`;
      }).join("")}</tbody>
    </table></div>`;
}

function renderOperations(trace) {
  const operations = trace.candidate_operations || [];
  return `<div class="operation-grid">${operations.map((operation) => `
    <article class="operation-card">
      <span>${escapeHtml(operation.kind)}</span>
      <h5>${escapeHtml(operation.title)}</h5>
      <p>${operation.from ? `<code>${escapeHtml(operation.from)} → ${escapeHtml(operation.to)}</code>` : `<code>${escapeHtml(operation.square || "")}</code>`}</p>
      ${operation.before !== undefined ? `<div>${pieceValueMarkup(operation.before)} <b>→</b> ${pieceValueMarkup(operation.after)}</div>` : ""}
      ${operation.piece_name ? `<small>${escapeHtml(operation.piece_name)}</small>` : ""}
    </article>
  `).join("")}</div>`;
}

function renderBoardCertificate(trace) {
  const certificate = trace.board_certificate || {};
  const edits = certificate.edits || certificate.changed_squares || [];
  const ranks = certificate.rank_checks || [];
  const sparse = edits.length > 0 || certificate.mode === "sparse" || certificate.mode === "compact";
  const sparseMarkup = sparse ? `
    <div class="sparse-summary">
      <div><span>表示模式</span><strong>${escapeHtml(certificate.mode || "sparse")}</strong></div>
      <div><span>局部编辑</span><strong>${escapeHtml(certificate.edit_count ?? edits.length)}</strong></div>
      <div><span>编辑失配</span><strong>${escapeHtml(certificate.mismatch_count ?? 0)}</strong></div>
      <div><span>精确全盘码</span><strong>${certificate.exact ? "成立" : "不成立"}</strong></div>
    </div>
    <div class="sparse-edit-grid">${edits.map((edit) => `
      <article class="sparse-edit ${edit.match === false ? "mismatch" : "match"}">
        <div><strong>${escapeHtml(edit.square)}</strong><span>index ${escapeHtml(edit.index)}</span></div>
        <p>${pieceValueMarkup(edit.before)}<b>→</b>${pieceValueMarkup(edit.actual ?? edit.expected)}</p>
        <small>${escapeHtml(edit.before_name || "走前")} → ${escapeHtml(edit.actual_name || edit.expected_name || "走后")}</small>
        <code>Δ = ${escapeHtml(edit.contribution)}</code>
        <pre>${escapeHtml(edit.litex_call || "")}</pre>
      </article>
    `).join("")}</div>
    <div class="board-code-card">
      <div><span>走前全盘码</span><code>${escapeHtml(certificate.before_code_hex || certificate.before_code)}</code></div>
      <div><span>走后全盘码</span><code>${escapeHtml(certificate.actual_after_code_hex || certificate.actual_after_code)}</code></div>
      <div><span>局部贡献和</span><code>${escapeHtml(certificate.delta_code)}</code></div>
      <p><strong>${certificate.exact ? "✓" : "✕"}</strong> after_code = before_code + ΣΔ。未列入编辑集合的格子不能被暗中修改。</p>
    </div>` : "";
  const legacyMarkup = ranks.length ? `
    <details class="legacy-rank-audit">
      <summary>展开旧版逐横线差分审计（${certificate.rank_check_count ?? ranks.length} 次 / ${certificate.legacy_cell_comparisons ?? ranks.length * 8} 格）</summary>
      <div class="rank-check-list">${ranks.map((rank) => `
        <details class="rank-check ${rank.match ? "match" : "mismatch"}" ${rank.pairs.some((pair) => pair.changed || !pair.match) ? "open" : ""}>
          <summary><span>第 ${rank.rank} 横线</span><strong>${rank.match ? "8/8 相等" : "存在失配"}</strong></summary>
          <div class="rank-pair-grid">${rank.pairs.map((pair) => `
            <div class="rank-pair ${pair.changed ? "changed" : ""} ${pair.match ? "" : "mismatch"}">
              <span>${escapeHtml(pair.square)}</span>
              <div>${pieceValueMarkup(pair.actual)}<i>=</i>${pieceValueMarkup(pair.expected)}</div>
              ${pair.changed ? `<small>走前 ${escapeHtml(pair.before_name)} → 候选 ${escapeHtml(pair.actual_name)}</small>` : ""}
            </div>
          `).join("")}</div>
          <pre>${escapeHtml(rank.litex_call)}</pre>
        </details>
      `).join("")}</div>
    </details>` : '<p class="legacy-disabled">生产模式没有生成 64 格逐项比较；需要差分审计时可切换 dual/legacy 模式。</p>';
  return `
    <p class="trace-explanation">${escapeHtml(certificate.explanation || "")}</p>
    ${sparseMarkup}
    ${legacyMarkup}`;
}

function renderMetadata(trace) {
  const metadata = trace.metadata_certificate;
  return `
    <p class="trace-explanation">${escapeHtml(metadata.explanation)}</p>
    <div class="trace-table-wrap"><table class="trace-table">
      <thead><tr><th>字段</th><th>走前</th><th>候选</th><th>期望</th></tr></thead>
      <tbody>${metadata.rows.map((row) => `
        <tr class="${row.match ? "match" : "mismatch"}"><th>${escapeHtml(row.label)}</th><td>${escapeHtml(row.before)}</td><td>${escapeHtml(row.candidate)}</td><td>${escapeHtml(row.expected)} ${row.match ? "✓" : "✕"}</td></tr>
      `).join("")}</tbody>
    </table></div>
    <div class="metadata-reasons">
      ${(metadata.castling_removed || []).map((item) => `<p><strong>移除 ${escapeHtml(item.right)}</strong>：${escapeHtml(item.reason)}</p>`).join("")}
      <p><strong>过路兵</strong>：${escapeHtml(metadata.ep_reason)}</p>
      <p><strong>半回合</strong>：${escapeHtml(metadata.halfmove_reason)}</p>
      <p><strong>完整回合</strong>：${escapeHtml(metadata.fullmove_reason)}</p>
    </div>`;
}

function renderSafety(trace) {
  const safety = trace.safety_certificate;
  return `
    <p class="trace-explanation warning">${escapeHtml(safety.explanation)}</p>
    <div class="safety-grid">${safety.stages.map((stage) => `
      <article class="safety-card ${stage.attacker_count === 0 ? "safe" : "unsafe"}">
        <div class="safety-top"><span>${escapeHtml(stage.label)}</span><strong>${stage.attacker_count === 0 ? "安全" : `${stage.attacker_count} 个攻击者`}</strong></div>
        <p>王位于 <code>${escapeHtml(stage.king_square)}</code>。${escapeHtml(stage.why)}</p>
        ${(stage.attackers || []).length ? `<ul>${stage.attackers.map((attacker) => `<li><b>${escapeHtml(attacker.piece_name)}</b> 从 <code>${escapeHtml(attacker.square)}</code> 攻击 <code>${escapeHtml(attacker.king_square)}</code>${attacker.blockers.length ? `；阻挡：${escapeHtml(attacker.blockers.join(", "))}` : "；路径无阻挡"}</li>`).join("")}</ul>` : ""}
      </article>
    `).join("")}</div>
    <div class="unsafe-total">汇总 unsafe_total = <strong>${safety.unsafe_total}</strong></div>`;
}

function renderTacticalEffects(trace) {
  const tactical = trace.tactical_effects;
  if (!tactical) return "";
  const afterCheckers = tactical.after_checkers || [];
  const checkerMarkup = afterCheckers.length
    ? `<div class="tactical-checkers">${afterCheckers.map((checker) => `
        <span><b>${escapeHtml(checker.piece_name)}</b><code>${escapeHtml(checker.square)}</code>${checker.path?.length ? `<small>${escapeHtml(checker.path.join(" → "))}</small>` : ""}</span>`).join("")}</div>`
    : '<p class="tactical-empty">候选走后没有棋子攻击对方王。</p>';
  const targets = (tactical.target_effects || []).map((target) => {
    const before = (target.before_attackers || []).map((item) => `${item.piece_name}@${item.square}`).join("、") || "无";
    const after = (target.after_attackers || []).map((item) => `${item.piece_name}@${item.square}`).join("、") || "无";
    const effect = target.opened ? "攻击线被打开" : target.closed ? "攻击线被关闭" : before === after ? "攻击关系未改变" : "攻击关系发生变化";
    return `<article class="tactical-target-card">
      <div><strong>${escapeHtml(target.label)}</strong><span>${escapeHtml(effect)}</span></div>
      <p><b>走前</b> ${escapeHtml(before)}</p>
      <p><b>走后</b> ${escapeHtml(after)}</p>
    </article>`;
  }).join("");
  return `
    <p class="trace-explanation warning">${escapeHtml(tactical.explanation)}</p>
    <div class="tactical-summary ${escapeHtml(tactical.kind)}">
      <div class="tactical-badge"><span>${escapeHtml(tactical.label)}</span><strong>${tactical.after_checker_count}</strong><small>走后攻击者</small></div>
      <div class="tactical-copy">
        <h5>对方王：<code>${escapeHtml(tactical.opponent_king_square_after)}</code></h5>
        <p>走前攻击者 ${tactical.before_checker_count} 个，走后 ${tactical.after_checker_count} 个；移动后的棋子${tactical.moved_piece_is_checker ? "本身也是将军者" : "不是直接将军者"}。</p>
        ${checkerMarkup}
      </div>
    </div>
    ${targets ? `<div class="tactical-target-grid">${targets}</div>` : ""}`;
}

function renderCertificate(trace, receipt) {
  const grouped = {};
  for (const call of trace.certificate.calls || []) {
    (grouped[call.group] ||= []).push(call);
  }
  return `
    <div class="certificate-groups">${Object.entries(grouped).map(([group, calls]) => `
      <details class="certificate-group">
        <summary><span>${escapeHtml(GROUP_NAMES[group] || group)}</span><strong>${calls.length} 条调用</strong></summary>
        <pre>${escapeHtml(calls.map((call) => call.source).join("\n"))}</pre>
      </details>
    `).join("")}</div>
    <details class="certificate-source">
      <summary>查看完整生成证书与 Litex 回执</summary>
      <div class="receipt-meta"><span>engine: <code>${escapeHtml(receipt.engine)}</code></span><span>sha256: <code>${escapeHtml(receipt.query_sha256)}</code></span><span>${escapeHtml(receipt.elapsed_ms)} ms</span></div>
      <pre>${escapeHtml(receipt.formal_source || trace.certificate.source || "")}</pre>
      ${(receipt.diagnostics || []).length ? `<pre class="diagnostic-block">${escapeHtml(receipt.diagnostics.join("\n"))}</pre>` : ""}
    </details>`;
}

function renderLabResult(result, lab) {
  if (!result) return '<div class="lab-result-placeholder">选择一个候选走法后，这里会展开完整状态迭代与 Litex 证书。</div>';
  const accepted = result.observed;
  const trace = result.trace;
  const changedSquares = (trace.board_certificate.changed_squares || []).map((item) => item.square);
  const statusText = accepted ? "Litex 接受：候选局面已提交" : "Litex 拒绝：候选局面未提交";
  const expectedText = result.ok ? "与教材预期一致" : "与教材预期不一致";
  return `
    <article class="lab-result-card ${accepted ? "accepted" : "rejected"}">
      <div class="lab-result-header">
        <div>
          <span>${escapeHtml(result.move.uci)}</span>
          <h4>${escapeHtml(statusText)}</h4>
          <p>${escapeHtml(expectedText)}。形状选择：<strong>${escapeHtml(trace.shape.name)}</strong>。</p>
        </div>
        <div class="result-seal">${accepted ? "✓" : "×"}</div>
      </div>

      <div class="shape-explainer">
        <strong>${escapeHtml(trace.shape.name)}</strong>
        <p>${escapeHtml(trace.shape.explanation)}</p>
        <span>路径：${trace.path.squares.length ? escapeHtml(trace.path.squares.join(" → ")) : "无中间格"}</span>
        <span>阻挡数：${trace.path.blocker_count}</span>
      </div>

      <div class="board-comparison">
        <figure><figcaption>走前局面</figcaption>${boardMarkup(result.before, { staticBoard: true, compact: true, orientation: lab.orientation })}</figure>
        <figure class="candidate"><figcaption>机械候选 after ${accepted ? "" : "（未提交）"}</figcaption>${boardMarkup(result.candidate_after, { staticBoard: true, compact: true, orientation: lab.orientation, changedSquares })}</figure>
        <figure class="committed"><figcaption>棋谱实际保留局面</figcaption>${boardMarkup(result.committed_after, { staticBoard: true, compact: true, orientation: lab.orientation, changedSquares: accepted ? changedSquares : [] })}</figure>
      </div>
      ${accepted ? "" : '<p class="rollback-note">机械候选仍被构造出来用于审计，但当前节点的 Position 与 FEN 完全不变。这就是 fail-closed 回滚。</p>'}

      <section class="trace-section"><h4>五阶段：一手棋并不只是移动两个格子</h4>${renderPipeline(trace)}</section>
      <section class="trace-section"><h4>candidate.py 实际执行的机械操作</h4>${renderOperations(trace)}</section>
      <section class="trace-section"><h4>FEN 六字段如何随 Position 更新</h4>${renderFenComparison(trace)}</section>
      <section class="trace-section"><h4>稀疏棋盘后继与精确全盘码</h4>${renderBoardCertificate(trace)}</section>
      <section class="trace-section"><h4>历史与计数元数据</h4>${renderMetadata(trace)}</section>
      <section class="trace-section"><h4>战术效果：将军、闪将、双将与牵制线</h4>${renderTacticalEffects(trace)}</section>
      <section class="trace-section"><h4>王安全证书与当前可信边界</h4>${renderSafety(trace)}</section>
      <section class="trace-section"><h4>Litex 具体调用</h4>${renderCertificate(trace, result.receipt)}</section>
    </article>`;
}

function renderBoardLabs(chapter) {
  const labs = chapter.board_labs || [];
  const section = byId("boardLabsSection");
  section.hidden = labs.length === 0;
  const grid = byId("boardLabGrid");
  grid.innerHTML = labs.map((lab) => {
    const result = state.boardResults.get(lab.id);
    const targets = targetMoveMap(lab);
    return `
      <article class="board-lab-card" id="lab-${escapeHtml(lab.id)}">
        <header class="board-lab-header">
          <div>
            <span>局面实验 · 第 ${escapeHtml(chapter.number)} 章</span>
            <h3>${escapeHtml(lab.title)}</h3>
            <p>${escapeHtml(lab.instruction)}</p>
          </div>
          <div class="concept-chips">${(lab.concepts || []).map((concept) => `<span>${escapeHtml(concept)}</span>`).join("")}</div>
        </header>
        <div class="board-lab-body">
          <div class="lab-board-column">
            ${boardMarkup(lab.fen, {
              orientation: lab.orientation,
              activeSquare: lab.active_square,
              marks: lab.marks,
              targetMoves: targets,
              labId: lab.id,
            })}
            ${stateChips(lab.fen)}
            ${markerLegend(lab)}
            <code class="fen-line">${escapeHtml(lab.fen)}</code>
          </div>
          <div class="lab-control-column">
            <div class="locked-piece-note"><span>锁定源格</span><strong>${escapeHtml(lab.active_square || "按按钮指定")}</strong><p>本实验不会让你随意移动其他棋子；每个按钮都对应目录中的固定 UCI 候选。</p></div>
            <div class="lab-move-list">${lab.moves.map((move) => {
              const expectedClass = move.expected ? "accept" : "reject";
              return `<button type="button" class="lab-move-button ${expectedClass}" data-lab-id="${escapeHtml(lab.id)}" data-move-id="${escapeHtml(move.id)}">
                <span><b>${escapeHtml(move.label)}</b><small>${escapeHtml(move.teaching)}</small></span>
                <em>${move.expected ? "预期接受" : "预期拒绝"}</em>
              </button>`;
            }).join("")}</div>
          </div>
        </div>
        <div class="board-lab-result">${renderLabResult(result, lab)}</div>
      </article>`;
  }).join("");

  grid.querySelectorAll(".lab-move-button").forEach((button) => {
    button.addEventListener("click", () => runBoardMove(button.dataset.labId, button.dataset.moveId));
  });
  grid.querySelectorAll(".candidate-square").forEach((button) => {
    button.addEventListener("click", () => {
      const lab = findCurrentLab(button.dataset.labId);
      const moves = (lab?.moves || []).filter((move) => move.uci.slice(2, 4) === button.dataset.targetSquare);
      if (moves.length === 1) runBoardMove(lab.id, moves[0].id);
      else if (moves.length > 1) toast("这个目标格对应多个候选（例如升变选择），请使用右侧按钮。", false);
    });
  });
}

function renderStatusResult(result, lab) {
  if (!result) return '<div class="status-result-placeholder">运行局面扫描后，这里会显示受将状态、合法着全集与终局分类。</div>';
  const analysis = result.analysis || {};
  const status = analysis.status || "ongoing";
  const legalMoves = analysis.legal_moves || [];
  const checkers = analysis.checkers || [];
  const dead = analysis.dead_position || {};
  return `
    <div class="status-result-card ${escapeHtml(STATUS_CLASSES[status] || status)}">
      <div class="status-result-head">
        <div>
          <span>${result.ok ? "与教材预期一致" : "与教材预期不一致"}</span>
          <h4>${escapeHtml(STATUS_LABELS[status] || status)}</h4>
          <p>${escapeHtml(result.reason || "")}</p>
        </div>
        <div class="status-seal">${status === "checkmate" ? "#" : status === "stalemate" ? "½" : status === "check" ? "+" : "•"}</div>
      </div>
      <div class="status-metric-grid">
        <div><span>正在受将</span><strong>${analysis.in_check ? "是" : "否"}</strong></div>
        <div><span>将军者</span><strong>${analysis.checker_count ?? 0}</strong></div>
        <div><span>候选着</span><strong>${analysis.candidate_count ?? 0}</strong></div>
        <div><span>Litex 接受的合法着</span><strong>${analysis.legal_move_count ?? 0}</strong></div>
      </div>
      <div class="status-detail-grid">
        <article>
          <h5>攻击当前王的棋子</h5>
          ${checkers.length ? `<ul>${checkers.map((checker) => `<li><b>${escapeHtml(checker.piece_name)}</b> 位于 <code>${escapeHtml(checker.square)}</code>${checker.path?.length ? `，射线路径 ${escapeHtml(checker.path.join(" → "))}` : ""}</li>`).join("")}</ul>` : "<p>没有攻击者；因此零合法着时才会归类为逼和，而不是将死。</p>"}
        </article>
        <article>
          <h5>全部合法应对</h5>
          ${legalMoves.length ? `<div class="legal-move-cloud">${legalMoves.map((move) => `<code title="${escapeHtml(move.after_fen)}">${escapeHtml(move.uci)}</code>`).join("")}</div>` : "<p>合法着集合为空。</p>"}
        </article>
      </div>
      <div class="dead-position-card ${dead.dead ? "dead" : "unknown"}">
        <strong>${dead.dead ? "死局识别：自动和棋" : "死局识别：保守算法不作结论"}</strong>
        <p>${escapeHtml(dead.reason || "")}</p>
      </div>
      <div class="draw-threshold-row">
        <span class="${analysis.fifty_move_claim_available ? "active" : ""}">五十回合申和 ${analysis.fifty_move_claim_available ? "已达到" : `未达到（halfmove=${analysis.halfmove ?? 0}）`}</span>
        <span class="${analysis.seventy_five_move_automatic ? "active automatic" : ""}">七十五回合自动和棋 ${analysis.seventy_five_move_automatic ? "已达到" : "未达到"}</span>
      </div>
      <p class="status-method-note">${escapeHtml(analysis.method || "")}</p>
    </div>`;
}

function renderStatusLabs(chapter) {
  const labs = chapter.status_labs || [];
  const section = byId("statusLabsSection");
  section.hidden = labs.length === 0;
  const grid = byId("statusLabGrid");
  grid.innerHTML = labs.map((lab) => {
    const result = state.statusResults.get(lab.id);
    return `
      <article class="status-lab-card" id="status-lab-${escapeHtml(lab.id)}">
        <header class="board-lab-header">
          <div><span>局面状态实验 · 第 ${escapeHtml(chapter.number)} 章</span><h3>${escapeHtml(lab.title)}</h3><p>${escapeHtml(lab.instruction)}</p></div>
          <div class="concept-chips">${(lab.concepts || []).map((concept) => `<span>${escapeHtml(concept)}</span>`).join("")}</div>
        </header>
        <div class="status-lab-body">
          <div class="lab-board-column">
            ${boardMarkup(lab.fen, { orientation: lab.orientation, marks: lab.marks, staticBoard: true })}
            ${stateChips(lab.fen)}
            ${markerLegend(lab)}
            <code class="fen-line">${escapeHtml(lab.fen)}</code>
          </div>
          <div class="status-lab-control">
            <div class="expected-status-card"><span>教材预期</span><strong>${escapeHtml(STATUS_LABELS[lab.expected_status] || lab.expected_status)}</strong><p>点击后会枚举几何候选，并把每个候选交给与工作台相同的 Litex 门禁。</p></div>
            <button class="run-status-lab" type="button" data-status-lab-id="${escapeHtml(lab.id)}">▶ 扫描全部合法着并分类</button>
          </div>
        </div>
        <div class="status-lab-result">${renderStatusResult(result, lab)}</div>
      </article>`;
  }).join("");
  grid.querySelectorAll(".run-status-lab").forEach((button) => {
    button.addEventListener("click", () => runStatusLab(button.dataset.statusLabId));
  });
}

function historyExpectationMarkup(expect = {}) {
  const labels = {
    occurrence: "最终重复次数",
    threefold_claim_available: "三次重复可申和",
    fivefold_automatic: "五次重复自动和棋",
    fifty_move_claim_available: "五十回合可申和",
    seventy_five_move_automatic: "七十五回合自动和棋",
  };
  return Object.entries(expect).map(([key, value]) => `<span><small>${escapeHtml(labels[key] || key)}</small><strong>${escapeHtml(String(value))}</strong></span>`).join("");
}

function timelineFlags(entry) {
  const flags = [];
  if (entry.threefold_claim_available) flags.push('<span class="claim">三次重复：可申和</span>');
  if (entry.fivefold_automatic) flags.push('<span class="automatic">五次重复：自动和棋</span>');
  if (entry.fifty_move_claim_available) flags.push('<span class="claim">50 回合：可申和</span>');
  if (entry.seventy_five_move_automatic) flags.push('<span class="automatic">75 回合：自动和棋</span>');
  return flags.join("") || '<span class="neutral">尚无和棋阈值事件</span>';
}

function renderHistoryResult(result, lab) {
  if (!result) return '<div class="history-result-placeholder">运行整段历史后，这里会按节点展开 FEN、重复键、出现次数与和棋阈值。</div>';
  const payload = result.result || {};
  const timeline = payload.timeline || [];
  const final = payload.final || {};
  const finalPosition = final.position || parseFen(lab.fen);
  return `
    <div class="history-result-card ${result.ok ? "success" : "failure"}">
      <div class="history-result-head">
        <div><span>${result.ok ? "历史实验通过" : "历史实验失败"}</span><h4>${escapeHtml(result.reason || "")}</h4></div>
        <strong>${timeline.length ? `${timeline.length - 1} plies` : "0 plies"}</strong>
      </div>
      <div class="history-board-pair">
        <figure><figcaption>起始局面</figcaption>${boardMarkup(lab.fen, { staticBoard: true, compact: true })}</figure>
        <figure><figcaption>最终已提交局面</figcaption>${boardMarkup(finalPosition, { staticBoard: true, compact: true })}</figure>
      </div>
      <div class="history-final-metrics">
        <div><span>最终重复次数</span><strong>${final.occurrence ?? "—"}</strong></div>
        <div><span>halfmove</span><strong>${final.position?.halfmove ?? "—"}</strong></div>
        <div><span>threefold</span><strong>${final.threefold_claim_available ? "可申和" : "否"}</strong></div>
        <div><span>fivefold</span><strong>${final.fivefold_automatic ? "自动和棋" : "否"}</strong></div>
        <div><span>50-move</span><strong>${final.fifty_move_claim_available ? "可申和" : "否"}</strong></div>
        <div><span>75-move</span><strong>${final.seventy_five_move_automatic ? "自动和棋" : "否"}</strong></div>
      </div>
      ${payload.failure ? `<pre class="history-failure">${escapeHtml(JSON.stringify(payload.failure, null, 2))}</pre>` : ""}
      <div class="history-timeline-wrap"><table class="history-timeline">
        <thead><tr><th>节点</th><th>本手</th><th>FEN / 重复键</th><th>次数</th><th>规则事件</th></tr></thead>
        <tbody>${timeline.map((entry) => `
          <tr class="${entry.fivefold_automatic || entry.seventy_five_move_automatic ? "automatic-row" : entry.threefold_claim_available || entry.fifty_move_claim_available ? "claim-row" : ""}">
            <td><b>${entry.ply}</b></td>
            <td><code>${escapeHtml(entry.uci || "ROOT")}</code></td>
            <td><code class="timeline-fen">${escapeHtml(entry.fen)}</code><code class="repetition-key">key: ${escapeHtml(entry.repetition_key?.key || "")}</code></td>
            <td><strong>${entry.occurrence}</strong><small>halfmove ${entry.position?.halfmove ?? "—"}</small></td>
            <td><div class="timeline-flags">${timelineFlags(entry)}</div></td>
          </tr>`).join("")}</tbody>
      </table></div>
      <details class="history-rule-notes" open><summary>规则解释与身份判定</summary>${Object.entries(payload.rules || {}).map(([key, text]) => `<p><code>${escapeHtml(key)}</code>${escapeHtml(text)}</p>`).join("")}</details>
    </div>`;
}

function renderHistoryLabs(chapter) {
  const labs = chapter.history_labs || [];
  const section = byId("historyLabsSection");
  section.hidden = labs.length === 0;
  const grid = byId("historyLabGrid");
  grid.innerHTML = labs.map((lab) => {
    const result = state.historyResults.get(lab.id);
    return `
      <article class="history-lab-card" id="history-lab-${escapeHtml(lab.id)}">
        <header class="board-lab-header">
          <div><span>历史实验 · 第 ${escapeHtml(chapter.number)} 章</span><h3>${escapeHtml(lab.title)}</h3><p>${escapeHtml(lab.instruction)}</p></div>
          <div class="concept-chips">${(lab.concepts || []).map((concept) => `<span>${escapeHtml(concept)}</span>`).join("")}</div>
        </header>
        <div class="history-lab-body">
          <div class="lab-board-column">${boardMarkup(lab.fen, { staticBoard: true, compact: false })}${stateChips(lab.fen)}<code class="fen-line">${escapeHtml(lab.fen)}</code></div>
          <div class="history-control-column">
            <div class="history-sequence"><span>固定走法序列</span><div>${(lab.sequence || []).map((uci, index) => `<code><b>${index + 1}</b>${escapeHtml(uci)}</code>`).join("") || "<em>不走子，只分析根局面</em>"}</div></div>
            <div class="history-expectation">${historyExpectationMarkup(lab.expect || {})}</div>
            <button class="run-history-lab" type="button" data-history-lab-id="${escapeHtml(lab.id)}">▶ 逐手验证并生成历史时间线</button>
          </div>
        </div>
        <div class="history-lab-result">${renderHistoryResult(result, lab)}</div>
      </article>`;
  }).join("");
  grid.querySelectorAll(".run-history-lab").forEach((button) => {
    button.addEventListener("click", () => runHistoryLab(button.dataset.historyLabId));
  });
}


function endgameIdsForChapter(chapter) {
  return [...new Set([...(chapter.endgame_courses || []), ...(chapter.interactive_endgames || [])])];
}

function endgameLesson(lessonId) {
  return (state.endgameCatalog || []).find((item) => item.lesson_id === lessonId) || null;
}

function endgameWorkbenchUrl(lesson, fen = null, hint = "") {
  const position = fen || lesson.fen;
  const params = new URLSearchParams({
    fen: position,
    lesson: lesson.lesson_id,
    title: lesson.title,
    goal: lesson.explanation,
    return: `/textbook#${currentChapter()?.slug || "interactive-endgames"}`,
  });
  if (hint) params.set("hint", hint);
  return `/?${params.toString()}`;
}

function endgameLessonCard(lesson) {
  return `<article class="endgame-course-card" data-endgame-lesson="${escapeHtml(lesson.lesson_id)}">
    <div class="endgame-course-board">${boardMarkup(lesson.fen, { staticBoard: true, compact: true })}</div>
    <div class="endgame-course-copy">
      <span>${lesson.goal === "dead-position" ? "死局识别" : "互动将杀训练"}</span>
      <h3>${escapeHtml(lesson.title)}</h3>
      <p>${escapeHtml(lesson.explanation)}</p>
      <ul>${(lesson.principles || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      <div class="endgame-course-actions">
        <button type="button" class="start-endgame" data-endgame-id="${escapeHtml(lesson.lesson_id)}">开始本课</button>
        <a href="${escapeHtml(endgameWorkbenchUrl(lesson))}">在工作台打开</a>
      </div>
    </div>
  </article>`;
}

function endgameStatusText(data) {
  const status = data?.analysis?.status || "ongoing";
  const map = { ongoing: "继续进行", check: "将军", checkmate: "将死", stalemate: "逼和" };
  if (data?.analysis?.dead_position?.dead) return "死局和棋";
  return map[status] || status;
}

function endgameBoardMarkup(data) {
  const position = parseFen(data.fen);
  const legalSources = new Set(data.legal_sources || []);
  const targets = new Set((data.legal_moves || [])
    .filter((move) => move.from === state.endgameSelectedSource)
    .map((move) => move.to));
  const squares = [];
  for (let rank = 8; rank >= 1; rank -= 1) {
    for (let fileIndex = 1; fileIndex <= 8; fileIndex += 1) {
      const file = String.fromCharCode(96 + fileIndex);
      const square = `${file}${rank}`;
      const piece = position.pieces[square] || 0;
      const classes = ["endgame-square", squareColor(fileIndex, rank)];
      if (legalSources.has(square)) classes.push("legal-source");
      if (square === state.endgameSelectedSource) classes.push("selected-source");
      if (targets.has(square)) classes.push("legal-target");
      squares.push(`<button type="button" class="${classes.join(" ")}" data-endgame-square="${square}" aria-label="${square}，${escapeHtml(PIECE_NAMES[piece] || "空格")}">
        <span class="endgame-piece">${PIECE_GLYPHS[piece] || ""}</span>
        ${fileIndex === 1 ? `<span class="endgame-rank">${rank}</span>` : ""}
        ${rank === 1 ? `<span class="endgame-file">${file}</span>` : ""}
        ${targets.has(square) ? '<span class="endgame-target-dot" aria-hidden="true"></span>' : ""}
      </button>`);
    }
  }
  return `<div class="endgame-board" role="grid" aria-label="互动残局棋盘">${squares.join("")}</div>`;
}

function renderEndgameSession() {
  const panel = byId("endgameTrainerPanel");
  if (!panel) return;
  const data = state.endgameSession;
  if (!data) {
    panel.innerHTML = '<div class="endgame-trainer-empty">选择上方课程后，系统会创建独立训练会话，并在这里显示可点击棋盘、合法目标、历史和 Litex 回执。</div>';
    return;
  }
  const lesson = data.lesson;
  const selectedMoves = (data.legal_moves || []).filter((move) => move.from === state.endgameSelectedSource);
  const history = data.history || [];
  const receipts = data.last_receipts || [];
  panel.innerHTML = `<article class="endgame-trainer-card ${data.finished ? "finished" : ""}">
    <header class="endgame-trainer-header">
      <div><span>TRAINING SESSION · ${escapeHtml(data.training_id)}</span><h3>${escapeHtml(lesson.title)}</h3><p>${escapeHtml(lesson.explanation)}</p></div>
      <strong>${escapeHtml(endgameStatusText(data))}</strong>
    </header>
    <div class="endgame-trainer-layout">
      <div class="endgame-board-column">
        ${endgameBoardMarkup(data)}
        ${stateChips(data.fen)}
        <code class="fen-line">${escapeHtml(data.fen)}</code>
      </div>
      <div class="endgame-trainer-controls">
        <div class="endgame-feedback">
          <span>当前提示</span>
          <p>${escapeHtml(data.feedback?.hint || "")}</p>
          ${data.feedback?.warning ? `<small>${escapeHtml(data.feedback.warning)}</small>` : ""}
        </div>
        <div class="endgame-selection">
          <span>选择</span>
          <strong>${state.endgameSelectedSource ? `已选源格 ${escapeHtml(state.endgameSelectedSource)}` : "绿色边框表示当前可走棋子"}</strong>
          <p>${state.endgameSelectedSource ? `合法目标：${selectedMoves.map((move) => move.to).join("、") || "无"}` : "先点击源格，再点击带圆点的目标格。"}</p>
        </div>
        <div class="endgame-metrics">
          <div><span>合法着</span><strong>${escapeHtml(data.analysis?.legal_move_count ?? data.legal_moves?.length ?? 0)}</strong></div>
          <div><span>将军者</span><strong>${escapeHtml(data.analysis?.checker_count ?? 0)}</strong></div>
          <div><span>王距</span><strong>${escapeHtml(data.feedback?.king_distance ?? "—")}</strong></div>
          <div><span>边线距</span><strong>${escapeHtml(data.feedback?.defender_edge_distance ?? "—")}</strong></div>
        </div>
        <div class="endgame-trainer-actions">
          <button type="button" data-endgame-action="restart" data-endgame-id="${escapeHtml(lesson.lesson_id)}">重新开始</button>
          <a href="${escapeHtml(endgameWorkbenchUrl(lesson, data.fen, data.feedback?.hint || ""))}">在工作台展开当前局面</a>
        </div>
      </div>
    </div>
    <div class="endgame-history-panel">
      <h4>训练走法记录</h4>
      ${history.length ? `<ol>${history.map((row) => `<li><span>${row.actor === "learner" ? "学习者" : "防守方"}</span><strong>${escapeHtml(row.san || row.uci)}</strong><code>${escapeHtml(row.uci)}</code><small>${escapeHtml(row.outcome || "")}</small></li>`).join("")}</ol>` : '<p>尚未走子。</p>'}
    </div>
    ${receipts.length ? `<details class="endgame-receipts"><summary>查看最近一轮的 Litex 证书回执（${receipts.length}）</summary>${receipts.map((receipt) => `<article><strong>${receipt.accepted ? "ACCEPT" : "REJECT"}</strong><code>${escapeHtml(receipt.query_sha256 || "")}</code><pre>${escapeHtml(receipt.agent_source || "")}</pre></article>`).join("")}</details>` : ""}
    ${data.finished ? `<div class="endgame-finished"><strong>训练结束：${escapeHtml(data.result)}</strong><p>${escapeHtml(data.feedback?.hint || "")}</p></div>` : ""}
  </article>`;
  panel.querySelectorAll("[data-endgame-square]").forEach((button) => {
    button.addEventListener("click", () => handleEndgameSquare(button.dataset.endgameSquare));
  });
  panel.querySelector('[data-endgame-action="restart"]')?.addEventListener("click", (event) => {
    startEndgameLesson(event.currentTarget.dataset.endgameId);
  });
}

async function startEndgameLesson(lessonId) {
  if (state.endgameBusy) return;
  state.endgameBusy = true;
  state.endgameSelectedSource = null;
  try {
    state.endgameSession = await request(`/api/textbook/endgames/${encodeURIComponent(lessonId)}/sessions`, { method: "POST", body: "{}" });
    renderEndgameSession();
    byId("endgameTrainerPanel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast(`已开始：${state.endgameSession.lesson.title}`);
  } catch (error) {
    toast(`无法开始残局课程：${error.message}`, true);
  } finally {
    state.endgameBusy = false;
  }
}

async function playEndgameMove(move) {
  if (!state.endgameSession || state.endgameBusy) return;
  state.endgameBusy = true;
  try {
    const payload = { from: move.from, to: move.to };
    if (move.promotion) payload.promotion = move.promotion;
    const data = await request(`/api/textbook/endgame-sessions/${encodeURIComponent(state.endgameSession.training_id)}/moves`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.endgameSession = data;
    state.endgameSelectedSource = null;
    renderEndgameSession();
    toast(data.accepted ? `Litex 接受 ${move.uci}` : `Litex 拒绝 ${move.uci}`, !data.accepted);
  } catch (error) {
    toast(`残局走法失败：${error.message}`, true);
  } finally {
    state.endgameBusy = false;
  }
}

function handleEndgameSquare(square) {
  const data = state.endgameSession;
  if (!data || data.finished || state.endgameBusy) return;
  const legalMoves = data.legal_moves || [];
  if (!state.endgameSelectedSource) {
    if (!(data.legal_sources || []).includes(square)) {
      toast("请选择绿色边框标出的己方棋子", true);
      return;
    }
    state.endgameSelectedSource = square;
    renderEndgameSession();
    return;
  }
  if (square === state.endgameSelectedSource) {
    state.endgameSelectedSource = null;
    renderEndgameSession();
    return;
  }
  const move = legalMoves.find((item) => item.from === state.endgameSelectedSource && item.to === square);
  if (move) {
    playEndgameMove(move);
    return;
  }
  if ((data.legal_sources || []).includes(square)) {
    state.endgameSelectedSource = square;
    renderEndgameSession();
    return;
  }
  toast("该目标不在当前合法着集合中", true);
}

function renderEndgameLabs(chapter) {
  const ids = endgameIdsForChapter(chapter);
  const section = byId("endgameLabsSection");
  const grid = byId("endgameLabGrid");
  const lessons = ids.map(endgameLesson).filter(Boolean);
  section.hidden = lessons.length === 0;
  if (!lessons.length) {
    grid.innerHTML = "";
    return;
  }
  grid.innerHTML = `<div class="endgame-course-grid">${lessons.map(endgameLessonCard).join("")}</div><div id="endgameTrainerPanel" class="endgame-trainer-panel"></div>`;
  grid.querySelectorAll(".start-endgame").forEach((button) => {
    button.addEventListener("click", () => startEndgameLesson(button.dataset.endgameId));
  });
  const activeLessonId = state.endgameSession?.lesson?.lesson_id;
  if (activeLessonId && ids.includes(activeLessonId)) renderEndgameSession();
  else {
    state.endgameSession = null;
    state.endgameSelectedSource = null;
    renderEndgameSession();
  }
}

function diagnosticText(result) {
  const diagnostics = result?.run?.diagnostics || [];
  if (diagnostics.length) return diagnostics.join("\n");
  const tail = result?.run?.output_tail || "";
  return tail ? tail.slice(-1200) : "未返回额外诊断。";
}

function renderExamples(chapter) {
  const grid = byId("exampleGrid");
  grid.innerHTML = "";
  for (const example of chapter.examples || []) {
    const result = state.exampleResults.get(example.id);
    const card = document.createElement("article");
    card.className = "example-card";
    const expectedClass = example.expected ? "accept" : "reject";
    const expectedText = example.expected ? "预期：接受" : "预期：拒绝";
    const resultClass = result ? (result.ok ? "success" : "failure") : "";
    const resultText = result
      ? `${result.ok ? "✓" : "✕"} 实际${result.observed ? "接受" : "拒绝"}，${result.ok ? "符合预期" : "不符合预期"}`
      : "尚未运行";
    card.innerHTML = `
      <div class="example-topline">
        <h3>${escapeHtml(example.title)}</h3>
        <span class="expected-badge ${expectedClass}">${expectedText}</span>
      </div>
      <pre class="example-query">${escapeHtml(example.query)}</pre>
      <p class="example-explanation">${escapeHtml(example.explanation)}</p>
      <div class="example-actions">
        <button class="run-example" type="button" data-example-id="${escapeHtml(example.id)}">▶ 运行局部谓词</button>
        <span class="example-result ${resultClass}">${escapeHtml(resultText)}</span>
      </div>
      ${result ? `<pre class="example-diagnostic">${escapeHtml(diagnosticText(result))}</pre>` : ""}
    `;
    card.querySelector(".run-example").addEventListener("click", () => runExample(example.id));
    grid.appendChild(card);
  }
}

function renderRunAllResult() {
  const result = state.runAllResult;
  const area = byId("sourceResult");
  if (!result) {
    area.innerHTML = `
      <div class="source-result-empty">
        <span>✓</span>
        <p>选择“编译整册”，即可用随包 Litex 编译教材，并核对核心定义镜像。</p>
      </div>`;
    return;
  }
  const success = Boolean(result.ok);
  const run = result.run || {};
  area.innerHTML = `
    <div class="source-result-card ${success ? "success" : "failure"}">
      <div class="result-symbol">${success ? "✓" : "!"}</div>
      <h3>${success ? "整份教材验证通过" : "教材验证未通过"}</h3>
      <p>${escapeHtml(result.reason || "")}</p>
      <div class="result-metrics">
        <div><span>顶层语句</span><strong>${run.statement_count ?? "—"}</strong></div>
        <div><span>成功语句</span><strong>${run.success_count ?? "—"}</strong></div>
        <div><span>退出码</span><strong>${run.returncode ?? "—"}</strong></div>
        <div><span>耗时</span><strong>${run.elapsed_ms != null ? `${run.elapsed_ms} ms` : "—"}</strong></div>
      </div>
    </div>`;
}

function renderChapter() {
  const chapter = currentChapter();
  if (!chapter) return;
  document.title = `第 ${chapter.number} 章 · ${chapter.title} — Litex 国际象棋规则教材`;
  byId("breadcrumbChapter").textContent = `第 ${chapter.number} 章`;
  byId("chapterKicker").textContent = `CHAPTER ${String(chapter.number).padStart(2, "0")}`;
  byId("chapterTitle").textContent = chapter.title;
  byId("chapterSummary").textContent = chapter.summary;
  byId("engineNote").textContent = chapter.engine_note;
  renderGoals(chapter);
  renderNarrative(chapter);
  renderStateFields(chapter);
  renderWorkflow(chapter);
  renderBoardLabs(chapter);
  renderStatusLabs(chapter);
  renderHistoryLabs(chapter);
  renderEndgameLabs(chapter);
  renderSource(chapter);
  renderExamples(chapter);
  renderRunAllResult();

  document.querySelectorAll(".chapter-link").forEach((button, index) => {
    button.classList.toggle("active", index === state.chapterIndex);
  });
  byId("previousChapter").disabled = state.chapterIndex === 0;
  byId("nextChapter").disabled = state.chapterIndex === state.catalog.chapters.length - 1;
  byId("chapterProgress").textContent = `${state.chapterIndex + 1} / ${state.catalog.chapters.length}`;
  history.replaceState(null, "", `#${chapter.slug}`);
}

function selectChapter(index) {
  if (!state.catalog?.chapters?.[index]) return;
  state.chapterIndex = index;
  renderChapter();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setBusy(busy) {
  state.busy = busy;
  byId("runAllButton").disabled = busy;
  document.querySelectorAll(".run-example, .lab-move-button, .candidate-square, .run-status-lab, .run-history-lab, .start-endgame, [data-endgame-action]").forEach((button) => {
    button.disabled = busy;
  });
}

function updateArtifactFromRun(result) {
  const status = byId("artifactStatus");
  status.className = `artifact-status ${result.ok ? "success" : "failure"}`;
  status.textContent = result.ok ? "全部通过" : "检查失败";
  const run = result.run || {};
  byId("statementStatus").textContent = run.statement_count != null
    ? `${run.success_count}/${run.statement_count} success`
    : "未执行";
  byId("statementStatus").className = result.ok ? "pass" : "fail";
  byId("elapsedStatus").textContent = run.elapsed_ms != null ? `${run.elapsed_ms} ms` : "—";
  byId("artifactCaption").textContent = result.reason || "教材验证完成";
  const output = byId("artifactOutput");
  const diagnostics = run.diagnostics || [];
  if (diagnostics.length) {
    output.hidden = false;
    output.textContent = diagnostics.join("\n");
  } else {
    output.hidden = true;
    output.textContent = "";
  }
}

async function runAll() {
  if (state.busy) return;
  setBusy(true);
  byId("artifactStatus").className = "artifact-status neutral";
  byId("artifactStatus").textContent = "Litex 运行中…";
  try {
    const result = await request("/api/textbook/verify", { method: "POST", body: "{}" });
    state.runAllResult = result;
    updateArtifactFromRun(result);
    renderRunAllResult();
    toast(result.ok ? "教材镜像与 Litex 编译全部通过" : "教材验证未通过", !result.ok);
  } catch (error) {
    byId("artifactStatus").className = "artifact-status failure";
    byId("artifactStatus").textContent = "请求失败";
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function runExample(exampleId) {
  if (state.busy) return;
  setBusy(true);
  try {
    const result = await request(`/api/textbook/examples/${encodeURIComponent(exampleId)}`, {
      method: "POST",
      body: "{}",
    });
    state.exampleResults.set(exampleId, result);
    renderExamples(currentChapter());
    toast(result.ok ? "局部谓词判定与教材预期一致" : "示例结果与预期不一致", !result.ok);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function runBoardMove(labId, moveId) {
  if (state.busy) return;
  setBusy(true);
  try {
    const result = await request(
      `/api/textbook/board-labs/${encodeURIComponent(labId)}/moves/${encodeURIComponent(moveId)}`,
      { method: "POST", body: "{}" },
    );
    state.boardResults.set(labId, result);
    renderBoardLabs(currentChapter());
    const target = document.getElementById(`lab-${labId}`)?.querySelector(".board-lab-result");
    target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast(
      result.ok
        ? `完整门禁${result.observed ? "接受" : "拒绝"} ${result.move.uci}，符合教材预期`
        : "完整门禁结果与教材预期不一致",
      !result.ok,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function runStatusLab(labId) {
  if (state.busy) return;
  setBusy(true);
  try {
    const result = await request(`/api/textbook/status-labs/${encodeURIComponent(labId)}`, { method: "POST", body: "{}" });
    state.statusResults.set(labId, result);
    renderStatusLabs(currentChapter());
    document.getElementById(`status-lab-${labId}`)?.querySelector(".status-lab-result")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast(result.ok ? `局面分类为：${STATUS_LABELS[result.observed_status] || result.observed_status}` : "局面状态与教材预期不一致", !result.ok);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function runHistoryLab(labId) {
  if (state.busy) return;
  setBusy(true);
  try {
    const result = await request(`/api/textbook/history-labs/${encodeURIComponent(labId)}`, { method: "POST", body: "{}" });
    state.historyResults.set(labId, result);
    renderHistoryLabs(currentChapter());
    document.getElementById(`history-lab-${labId}`)?.querySelector(".history-lab-result")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast(result.ok ? "历史序列、重复键与阈值全部符合教材预期" : "历史实验与教材预期不一致", !result.ok);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function resetResults() {
  state.runAllResult = null;
  state.exampleResults.clear();
  state.boardResults.clear();
  state.statusResults.clear();
  state.historyResults.clear();
  state.endgameSession = null;
  state.endgameSelectedSource = null;
  byId("artifactStatus").className = "artifact-status neutral";
  byId("artifactStatus").textContent = "尚未运行";
  byId("statementStatus").textContent = "—";
  byId("statementStatus").className = "";
  byId("elapsedStatus").textContent = "—";
  byId("artifactOutput").hidden = true;
  byId("artifactCaption").textContent = "检查教材镜像、章节标记与 Litex 编译结果";
  renderChapter();
}

async function initialize() {
  try {
    const [catalog, source, status, endgames] = await Promise.all([
      request("/textbook-source/chapters.json"),
      fetch("/textbook-source/chess_rules_textbook_cn.lit").then((response) => {
        if (!response.ok) throw new Error(`无法读取教材源码：HTTP ${response.status}`);
        return response.text();
      }),
      request("/api/textbook/status"),
      request("/api/textbook/endgames"),
    ]);
    state.catalog = catalog;
    state.source = source;
    state.status = status;
    state.endgameCatalog = endgames.lessons || [];
    const requested = window.location.hash.replace(/^#/, "");
    const index = catalog.chapters.findIndex((chapter) => chapter.slug === requested);
    state.chapterIndex = index >= 0 ? index : 0;
    renderSidebar();
    updateRuntime(status);
    renderChapter();
  } catch (error) {
    byId("chapterTitle").textContent = "教材加载失败";
    byId("chapterSummary").textContent = error.message;
    toast(error.message, true);
  }
}

byId("runAllButton").addEventListener("click", runAll);
byId("resetButton").addEventListener("click", resetResults);
byId("previousChapter").addEventListener("click", () => selectChapter(state.chapterIndex - 1));
byId("nextChapter").addEventListener("click", () => selectChapter(state.chapterIndex + 1));
window.addEventListener("hashchange", () => {
  if (!state.catalog) return;
  const slug = window.location.hash.replace(/^#/, "");
  const index = state.catalog.chapters.findIndex((chapter) => chapter.slug === slug);
  if (index >= 0 && index !== state.chapterIndex) {
    state.chapterIndex = index;
    renderChapter();
  }
});

initialize();
