# Embed Litex Chess into the Litex textbook website

This directory is the host-side integration layer for v0.9. The chess UI is no
longer required to own the page header, textbook sidebar, or application-level
navigation. The Litex host owns those elements and mounts one of two custom
elements into its normal route outlet:

```html
<script type="module" src="/extensions/chess/embed/litex-chess-elements.js"></script>

<litex-chess-textbook
  api-base="/api"
  source-base="/textbook-source"
  chapter-base="/textbook/Chess"
  workbench-base="/textbook/Chess/workbench"
  chapter="position-state">
</litex-chess-textbook>
```

or:

```html
<litex-chess-workbench
  api-base="/api"
  textbook-base="/textbook/Chess">
</litex-chess-workbench>
```

Both components use Shadow DOM for CSS isolation, but they are real elements in
the Litex document—not iframes. Links, history, accessibility events, and the
host's global navigation remain part of one page.

## Files the Litex site needs

1. Publish this package's `frontend/` directory at `/extensions/chess/`.
2. Mount the chess API at `/api` or set a different `api-base`.
3. Publish `textbook/` at `/textbook-source/`, or proxy the two API endpoints
   `/api/textbook/catalog` and `/api/textbook/source`.
4. Copy `integration/golitex-overlay/textbooks/Chess/` to the public Litex
   repository's `textbooks/Chess/` directory so the book also has native `.lit`
   source and `litex.config` registration.
5. Register routes under `/textbook/Chess/:slug` and
   `/textbook/Chess/workbench`. `register-chess.js` provides a
   framework-neutral adapter.

## Host contract

The optional host object passed to `registerLitexChess(host)` may implement:

```js
host.registerTextbook(bookDescriptor)
host.registerRoute(path, asyncRouteHandler)
```

A route handler receives `{ outlet, url }`. `outlet` is the main Litex content
container. The adapter replaces only its children; it does not alter the Litex
header or sidebar.

## Upstream boundary

The public `litexlang/golitex` repository exposes the textbook source layout
but not the production website implementation. Consequently this package does
not pretend to patch a private frontend repository. It provides:

- a native `textbooks/Chess` overlay following the public repository's module
  convention;
- a no-iframe Web Component extension;
- a framework-neutral route adapter;
- a Litex-style development host at `/textbook/Chess/...` for integration
  testing.

The overlay and compatibility tests are pinned to public `golitex` commit
`2e457026928e009344d35f363e721c2540c410b6`.

## Static asset installer

To copy the web extension into an existing site's public directory without
modifying its router:

```bash
python integration/install_web_assets.py /path/to/site/public --overwrite
```

Then load `/extensions/chess/embed/litex-chess-elements.js` and connect the
routes using `register-chess.js`. The exact host contract is documented in
`HOST_INTEGRATION_CONTRACT_CN.md`.
