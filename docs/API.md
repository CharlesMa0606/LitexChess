# API overview

The live OpenAPI page is available at `/docs` after startup.

## Service and source

- `GET /api/health`
- `GET /api/formal/source`

## Workbench sessions

- `POST /api/sessions` — create from a FEN.
- `GET /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/move`
- `POST /api/sessions/{session_id}/goto`
- `GET /api/sessions/{session_id}/nodes/{node_id}/receipt`
- `GET /api/sessions/{session_id}/export-pgn`
- `PUT /api/sessions/{session_id}/headers`
- `POST /api/import-pgn`

A move body uses:

```json
{"from":"e2","to":"e4","promotion":null,"parent_id":"optional-node-id"}
```

## Textbook

- `GET /api/textbook/status`
- `POST /api/textbook/verify`
- `POST /api/textbook/examples/{example_id}`
- `GET /api/textbook/board-labs/{lab_id}`
- `POST /api/textbook/board-labs/{lab_id}/moves/{move_id}`
- `POST /api/textbook/status-labs/{lab_id}`
- `POST /api/textbook/history-labs/{lab_id}`

## Endgame trainer

- `GET /api/textbook/endgames`
- `GET /api/textbook/endgames/{lesson_id}`
- `POST /api/textbook/endgames/{lesson_id}/sessions`
- `GET /api/textbook/endgame-sessions/{training_id}`
- `POST /api/textbook/endgame-sessions/{training_id}/moves`
- `DELETE /api/textbook/endgame-sessions/{training_id}`

All accepted learner and automatic-defender moves include ordinary Litex receipts.
