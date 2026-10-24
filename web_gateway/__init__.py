"""Unmodified JKDF2Web transport adapter for the dedicated server."""

from .ipc import NativeIPC, EngineUnavailable, ProtocolError

__all__ = ["NativeIPC", "EngineUnavailable", "ProtocolError"]
