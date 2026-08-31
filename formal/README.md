# Production Litex kernel

`chess_rules.lit` is the only Litex module loaded by the interactive move gate.
It contains the concrete predicates used by one move certificate:

1. a readable `move(e2, e4)` / `result(checkmate)` envelope plus a finite result witness;
2. piece geometry, ownership, occupancy and path conditions;
3. a 2–4-square sparse board delta with an exact base-16 board code;
4. FEN metadata equality;
5. king-safety and final zero-mismatch contracts.

Algebraic square and outcome names are local query aliases rather than 64 global constants. The former `board_rank_transition` predicate is not part of the production kernel; `compact_transition.py` only preserves compatibility with archived query fixtures.

Research blueprints and unfinished relational interfaces live under `research/formal/`. They are compiled by a separate verification gate and are never loaded as production rules.
