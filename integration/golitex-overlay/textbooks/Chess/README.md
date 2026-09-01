# Chess textbook overlay for `litexlang/golitex`

This directory is designed to be copied verbatim to `textbooks/Chess/` in the
public Litex repository. It follows the repository's module-style textbook
convention: `litex.config` exports the shared rule kernel first and then the
fifteen chapter files in source order.

The `.lit` files are the native, independently runnable fallback. The richer
board, move certificates, exercises, and endgame trainer are supplied by the
site extension under `integration/litex-site/`; they mount directly into the
Litex textbook route as custom elements and do not use an iframe.

From a Litex checkout, run:

```text
target/release/litex -compact -runner -r textbooks/Chess
```

The overlay was prepared against public `golitex` main commit
`2e457026928e009344d35f363e721c2540c410b6` (2026-08-18). Re-run the included
compatibility checks when the upstream textbook loader changes.
