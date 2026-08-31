# Architecture

## Runtime path

```text
Browser
  -> FastAPI request
  -> SessionStore / EndgameTrainer
  -> candidate.apply_candidate
  -> LitexQueryBuilder.build_move_query
  -> Gate.validate_move
  -> persistent Litex process
  -> commit node or rollback
```

The browser never receives a precomputed legality table. A drag or click only proposes a move. The backend constructs a candidate state and a concrete certificate; Litex is the final authority for committing that edge.

## Core objects

- `Position`: board, side to move, castling rights, en-passant square, halfmove clock and fullmove number.
- `Move`: source, target and optional promotion.
- `CandidateTransition`: immutable before state, proposed move and mechanically constructed after state.
- `BuiltQuery`: actual Litex source, SHA-256, Agent-facing source and outcome summary.
- `ProofReceipt`: accept/reject result, diagnostics, elapsed time and persisted source.
- `GameTree`: branching PGN-compatible node tree; each accepted node stores its own `Position` and receipt.

## Modules

- `model.py`: FEN, coordinates and immutable domain objects.
- `candidate.py`: mechanical candidate application; no legality authorization.
- `agent_record.py`: compact `move(...)` / `result(...)` record.
- `query.py`: concrete certificate compiler.
- `compact_transition.py`: exact sparse board delta and legacy-fixture conversion.
- `litex_gate.py`: fail-closed persistent verifier integration.
- `fast_state.py`: finite legal-move generation used for status aggregation.
- `game_status.py`: checkmate, stalemate, dead-position and repetition/history summaries.
- `game_tree.py`, `pgn.py`, `presentation.py`: tree, PGN and SAN.
- `textbook.py`: generated textbook mirror and fixed labs.
- `endgame_training.py`: interactive lessons; all committed moves reuse the ordinary gate.
- `api.py`: HTTP application factory and routes.

## Source separation

```text
formal/chess_rules.lit        only production Litex kernel
textbook/chess_rules_...lit   generated commented mirror
research/formal/              non-runtime relational blueprints
```

`formal/RUNTIME_KERNEL.txt` is an explicit manifest and currently names only `chess_rules.lit`.

## Frontend

- `/`: workbench, board, move tree, proof receipt and three source views.
- `/textbook`: fifteen-chapter visual curriculum, fixed labs and endgame trainer.
- Both pages reuse the same API and state model. Textbook links pass FEN and lesson context to the workbench through query parameters.
