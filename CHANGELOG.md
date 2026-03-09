# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.2] - 2026-03-09

### Added

- Sans-I/O PostgreSQL wire protocol (v3.0 and v3.2) codec.
- `BackendMessageDecoder` and `FrontendMessageDecoder` for incremental zero-copy message parsing.
- Complete coverage of all official PostgreSQL protocol messages.
- `FrontendStateMachine` and `BackendStateMachine` for protocol phase validation.
- `FrontendConnection` and `BackendConnection` coordinating decoder and state machine.
- `py.typed` marker for PEP 561 typed package support.

[Unreleased]: https://github.com/DHUKK/pygwire/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/DHUKK/pygwire/releases/tag/v0.0.1
