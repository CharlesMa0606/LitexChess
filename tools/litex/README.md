# Bundled Litex executables

This development bundle includes the official Litex `0.9.116-beta` release
executables for Linux x86-64 and Windows x86-64 so the chess prototype can be
started without compiling Rust first.

- Linux: `linux-amd64/litex`
- Windows: `windows-amd64/litex.exe`
- Checksums: `SHA256SUMS`
- Upstream source pin: `../../litex.lock`
- Upstream license: `../../third_party/Litex-LICENSE.txt`

The application checks `LITEX_BIN` / `LITEXPY_LITEX_BIN` first. The supplied run
scripts set those variables to the bundled executable. `scripts/bootstrap_litex.sh`
remains available for rebuilding the exact pinned source commit.
