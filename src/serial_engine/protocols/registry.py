"""Protocol parser registry.

Plugins register a :class:`ProtocolParser` subclass under a name; the rest of
the application refers to parsers by name, so new protocols never require a UI
rewrite.
"""

from __future__ import annotations

import logging

from .base import ProtocolParser

logger = logging.getLogger(__name__)


class ProtocolRegistry:
    """A registry plus factory for protocol parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, type[ProtocolParser]] = {}

    def register(self, name: str, parser_cls: type[ProtocolParser]) -> None:
        """Register *parser_cls* under *name* (overwrites any existing entry)."""
        if name in self._parsers:
            logger.debug("Re-registering protocol %r", name)
        self._parsers[name] = parser_cls
        logger.debug("Registered protocol %r -> %s", name, parser_cls.__name__)

    def create(self, name: str) -> ProtocolParser:
        """Instantiate the parser registered under *name*."""
        try:
            parser_cls = self._parsers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown protocol {name!r}") from exc
        return parser_cls()

    def names(self) -> list[str]:
        """Return the sorted list of registered protocol names."""
        return sorted(self._parsers)

    def __contains__(self, name: str) -> bool:
        return name in self._parsers

    def __len__(self) -> int:
        return len(self._parsers)


#: Default registry instance used across the application.
registry = ProtocolRegistry()


def register(name: str):
    """Class decorator registering a parser with the default registry."""

    def decorator(cls: type[ProtocolParser]) -> type[ProtocolParser]:
        registry.register(name, cls)
        return cls

    return decorator
