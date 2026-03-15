# Changelog

## [0.1.0] — Initial release

### Added
- `relay server start` — WebSocket relay mediator with Ed25519 cert issuance and JSONL audit logging
- `relay-agent` — server-side daemon, dials outbound (no inbound ports needed)
- `relay deploy` — chunked file/directory deploy with tar.gz packing and post-deploy hooks
- `relay exec` — remote command execution with stdout/stderr/exit_code
- `relay ssh` — interactive shell through relay tunnel
- `relay ping` — latency measurement
- `relay status` — check which agents are online
- `relay add / remove / list` — server profile management
- `relay logs` — tail audit log
- Python SDK (`RelayClient`) with async context manager
- Short-lived session certificates (Ed25519 signed, 15-min TTL, cached until near-expiry)
- Full test suite: unit tests (crypto, protocol, config, CLI) + integration tests (real server+agent+client)
- VS Code launch/tasks/settings for Copilot-assisted development
- Termux/Android support
- Examples: quickstart, SDK usage, Termux connect
