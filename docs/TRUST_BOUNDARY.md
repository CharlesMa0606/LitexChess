# Trust boundary

## Acceptance authority

An edge is committed only when the Litex gate accepts the entire concrete certificate. There is no Stockfish/python-chess legality fallback. Missing verifier, timeout, malformed output, unknown status or failed statement means reject.

## Host-side trusted computation

Python currently computes:

- candidate state application;
- movement-predicate selection;
- ray/path and blocker counts;
- canonical sparse edits and exact board-code parameters;
- expected metadata values;
- attacker enumeration and safety counts;
- finite legal-move sets used for checkmate/stalemate;
- repetition keys and teaching labels;
- deterministic endgame defender ordering.

These computations are auditable and regression-tested, but they remain part of the trusted computing base.

## Litex-checked facts

Litex checks:

- coordinate, piece and side domains;
- source ownership and selected movement relation;
- path-clear and special-move conditions;
- each sparse edit and the exact global code increment;
- metadata equality;
- supplied king/safety summaries;
- final zero-mismatch transition contract.

## Status aggregation

`fast_state.py` cannot approve a move. It is used only after candidate construction to aggregate `check`, `checkmate`, `stalemate` and legal-reply counts. Every move actually stored in the workbench or endgame trainer still goes through `Gate.validate_move`.

## Research boundary

`research/formal/` contains compilable interfaces for a more relational design. They are not silently loaded by the runtime and must not be presented as completed production theorems.
