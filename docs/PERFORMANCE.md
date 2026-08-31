# Performance notes

## Board certificates

Production queries contain two to four sparse square edits plus one exact board-code equation. They do not transmit 64 actual/expected pairs.

## Status generation

`fast_state.py` starts from the pieces that actually exist and uses piece-specific move generators. At the initial position it produces 20 legal moves rather than attempting 4096 source-target pairs. Perft depth 1 and 2 are regression-tested as 20 and 400.

## Persistent verifier

The normal gate uses a persistent Litex process, avoiding process startup for every statement. The entire move certificate is treated transactionally; performance optimization must not bypass the fail-closed result.

## Caching

Game-state summaries are deterministic for a complete FEN and can be reused for SAN, textbook status and repeated node views. The current project favors transparent bounded computation over aggressive opaque caches.
