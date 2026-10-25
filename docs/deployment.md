# Deployment

Arbora runs separately from `tuig`. The frontend does not start an agent runtime
or import backend internals. PyPI binary-wheel qualification initially targets
Linux x86_64 and aarch64. macOS, Windows and container images are not qualified
by those receipts. The retired Python container recipe is no longer shipped.

Use TLS and a bearer credential for remote services. Never place credentials in
repository configuration or command examples.
