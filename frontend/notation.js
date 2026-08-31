"use strict";

(function exposeNotation(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LitexChessNotation = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function notationFactory() {
  function nodeFor(tree, nodeId) {
    return tree?.nodes?.[nodeId] || null;
  }

  function isWhiteTurn(position) {
    return position?.turn === "white" || position?.turn === 1;
  }

  function moveText(node) {
    return node?.san || node?.move?.uci || "?";
  }

  function notationPrefix(position, lineStart = false) {
    if (!position) return "";
    if (isWhiteTurn(position)) return `${position.fullmove}.`;
    return lineStart ? `${position.fullmove}...` : "";
  }

  function annotationTokens(node) {
    const tokens = [];
    for (const nag of node?.nags || []) {
      tokens.push({ kind: "nag", text: String(nag) });
    }
    if (node?.comment) {
      tokens.push({ kind: "comment", text: `{${String(node.comment)}}` });
    }
    return tokens;
  }

  function buildVariationTokens(
    tree,
    parentId,
    childId,
    { lineStart = false, includeSiblings = true, trail = new Set() } = {},
  ) {
    const edgeKey = `${parentId}->${childId}`;
    if (trail.has(edgeKey)) throw new Error(`cyclic notation edge: ${edgeKey}`);

    const parent = nodeFor(tree, parentId);
    const child = nodeFor(tree, childId);
    if (!parent || !child) return [];

    const nextTrail = new Set(trail);
    nextTrail.add(edgeKey);
    const tokens = [];
    const prefix = notationPrefix(parent.position, lineStart);
    if (prefix) tokens.push({ kind: "prefix", text: prefix });
    tokens.push({ kind: "move", nodeId: childId, text: moveText(child) });
    tokens.push(...annotationTokens(child));

    // The selected continuation stays horizontal.  Alternative replies at the
    // same position are inserted as recursive parenthesised lines.
    if (includeSiblings) {
      for (const alternateId of parent.children || []) {
        if (alternateId === childId) continue;
        tokens.push({ kind: "paren", text: "(" });
        tokens.push(
          ...buildVariationTokens(tree, parentId, alternateId, {
            lineStart: true,
            includeSiblings: false,
            trail: nextTrail,
          }),
        );
        tokens.push({ kind: "paren", text: ")" });
      }
    }

    const nextId = child.children?.[0];
    if (nextId) {
      tokens.push(
        ...buildVariationTokens(tree, childId, nextId, {
          lineStart: false,
          includeSiblings: true,
          trail: nextTrail,
        }),
      );
    }
    return tokens;
  }

  function buildVariationBlock(tree, parentId, mainChildId) {
    const parent = nodeFor(tree, parentId);
    const alternatives = (parent?.children || []).filter((id) => id !== mainChildId);
    if (!alternatives.length) return null;

    const tokens = [];
    alternatives.forEach((alternateId, index) => {
      // The first side line is written directly, as requested.  Additional
      // sibling lines are wrapped in parentheses on the same horizontal stream.
      if (index > 0) tokens.push({ kind: "paren", text: "(", topLevel: true });
      tokens.push(
        ...buildVariationTokens(tree, parentId, alternateId, {
          lineStart: true,
          includeSiblings: false,
        }),
      );
      if (index > 0) tokens.push({ kind: "paren", text: ")", topLevel: true });
    });
    return { type: "variation", parentId, mainChildId, tokens };
  }

  function buildNotationBlocks(tree) {
    if (!tree?.root_id || !tree?.nodes?.[tree.root_id]) return [];

    const blocks = [];
    let parentId = tree.root_id;
    let pendingRow = null;
    const visited = new Set();

    while (nodeFor(tree, parentId)?.children?.length) {
      if (visited.has(parentId)) throw new Error(`cyclic main line at node: ${parentId}`);
      visited.add(parentId);

      const parent = nodeFor(tree, parentId);
      const mainChildId = parent.children[0];
      const fullmove = parent.position.fullmove;
      const whiteToMove = isWhiteTurn(parent.position);

      if (whiteToMove) {
        if (pendingRow) blocks.push({ type: "row", ...pendingRow });
        pendingRow = {
          fullmove,
          whiteId: mainChildId,
          blackId: null,
          leadingEllipsis: false,
          trailingEllipsis: false,
        };
      } else if (pendingRow && pendingRow.fullmove === fullmove && !pendingRow.blackId) {
        pendingRow.blackId = mainChildId;
      } else {
        if (pendingRow) blocks.push({ type: "row", ...pendingRow });
        pendingRow = {
          fullmove,
          whiteId: null,
          blackId: mainChildId,
          leadingEllipsis: true,
          trailingEllipsis: false,
        };
      }

      const variation = buildVariationBlock(tree, parentId, mainChildId);
      if (variation) {
        if (whiteToMove && pendingRow && !pendingRow.blackId) {
          pendingRow.trailingEllipsis = true;
        }
        if (pendingRow) blocks.push({ type: "row", ...pendingRow });
        pendingRow = null;
        blocks.push(variation);
      }

      parentId = mainChildId;
    }

    if (pendingRow) blocks.push({ type: "row", ...pendingRow });
    return blocks;
  }

  function tokensToText(tokens) {
    return (tokens || [])
      .map((token) => token.text)
      .filter(Boolean)
      .join(" ")
      .replace(/\(\s+/g, "(")
      .replace(/\s+\)/g, ")")
      .replace(/\s+([,.;:!?])/g, "$1")
      .trim();
  }

  function formatNotationText(tree) {
    const lines = [];
    for (const block of buildNotationBlocks(tree)) {
      if (block.type === "variation") {
        lines.push(`│ ${tokensToText(block.tokens)}`);
        continue;
      }
      const white = block.whiteId ? moveText(nodeFor(tree, block.whiteId)) : "";
      const black = block.blackId ? moveText(nodeFor(tree, block.blackId)) : "";
      const whiteCell = white || (block.leadingEllipsis ? "..." : "");
      const blackCell = black || (block.trailingEllipsis ? "..." : "");
      lines.push(`${block.fullmove}. ${whiteCell}${blackCell ? ` ${blackCell}` : ""}`.trim());
    }
    return lines.join("\n");
  }

  return {
    buildNotationBlocks,
    buildVariationBlock,
    buildVariationTokens,
    formatNotationText,
    notationPrefix,
    tokensToText,
  };
});
