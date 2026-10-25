# Deployment

Central Arbora runs separately from `tuig` by default. Explicit experimental
local mode starts an internal `arbora-acp` child, not another frontend. The native
frontend does not import backend internals. See [configuration](configuration.md)
for helper lookup and the unqualified installed-backend boundary. PyPI binary-wheel qualification initially targets
Linux x86_64 and aarch64. macOS, Windows and container images are not qualified
by those receipts. The retired Python container recipe is no longer shipped.

Use TLS and a bearer credential for remote services. Never place credentials in
repository configuration or command examples.
