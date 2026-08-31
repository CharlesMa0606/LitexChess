#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const notation = require(path.join(__dirname, "..", "frontend", "notation.js"));

function node(id, turn, fullmove, san = null, children = [], extras = {}) {
  return {
    id,
    san,
    move: san ? { uci: san.toLowerCase().replaceAll(/[+#x=-]/g, "") } : null,
    children,
    comment: extras.comment || "",
    nags: extras.nags || [],
    position: { turn, fullmove, fen: `${id} ${turn} ${fullmove}` },
  };
}

const tree = {
  root_id: "root",
  current_id: "oo",
  nodes: {
    root: node("root", "white", 4, null, ["d3", "nc3"]),
    d3: node("d3", "black", 4, "d3", ["bc5"]),
    bc5: node("bc5", "white", 5, "Bc5", ["oo"]),
    oo: node("oo", "black", 5, "O-O"),

    nc3: node("nc3", "black", 4, "Nc3", ["d5"]),
    d5: node("d5", "white", 5, "d5", ["exd5"]),
    exd5: node("exd5", "black", 5, "exd5", ["nxd5"]),
    nxd5: node("nxd5", "white", 6, "Nxd5", ["bxd5"]),
    bxd5: node("bxd5", "black", 6, "Bxd5", ["qxd5", "qf6"]),
    qxd5: node("qxd5", "white", 7, "Qxd5", ["nxd5w"]),
    nxd5w: node("nxd5w", "black", 7, "Nxd5"),
    qf6: node("qf6", "white", 7, "Qf6", ["bxc6w"]),
    bxc6w: node("bxc6w", "black", 7, "Bxc6+", ["bxc6b"]),
    bxc6b: node("bxc6b", "white", 8, "bxc6"),
  },
};

const expected = [
  "4. d3 ...",
  "│ 4. Nc3 d5 5. exd5 Nxd5 6. Bxd5 Qxd5 (6... Qf6 7. Bxc6+ bxc6) 7. Nxd5",
  "4. ... Bc5",
  "5. O-O",
].join("\n");

const actual = notation.formatNotationText(tree);
assert.equal(actual, expected);
const blocks = notation.buildNotationBlocks(tree);
assert.deepEqual(blocks.map((block) => block.type), ["row", "variation", "row", "row"]);
assert.equal(blocks.filter((block) => block.type === "variation").length, 1);
assert.match(actual, /\(6\.\.\. Qf6 7\. Bxc6\+ bxc6\)/);
assert.doesNotMatch(actual, /\n\s{2,}│/);

const blackStart = {
  root_id: "root",
  current_id: "qd7",
  nodes: {
    root: node("root", "black", 12, null, ["qd7"]),
    qd7: node("qd7", "white", 13, "Qd7"),
  },
};
assert.equal(notation.formatNotationText(blackStart), "12. ... Qd7");

const cyclic = {
  root_id: "root",
  current_id: "root",
  nodes: {
    root: node("root", "white", 1, null, ["a"]),
    a: node("a", "black", 1, "a4", ["root"]),
  },
};
assert.throws(() => notation.buildNotationBlocks(cyclic), /cyclic/);

console.log("notation_smoke=PASS");
console.log(actual);
