# Notices

Litex Chess Studio is an independent development prototype.

The bundle includes official Litex 0.9.116-beta executables from the public
`litexlang/golitex` project. Litex is distributed under the Apache License 2.0;
its license text is copied to `third_party/Litex-LICENSE.txt`, and the exact
release/commit is recorded in `litex.lock`.

The optional `litexpy` Python runner is not bundled. When installed, the backend
uses it for a persistent Litex session; otherwise it uses the bundled official
Litex CLI in fail-closed one-shot runner mode.

Unicode chess glyphs are rendered from fonts already installed on the end
user's system. No font files are included.
