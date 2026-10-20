"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal Provider Resolver

Enforces a strict whitelist-only registry of authorized MultimodalInferenceProvider instances.
Forbids dynamic importing, arbitrary string evaluation, and class path traversal.
"""

import logging
from threading import Lock
from typing import Callable, Optional

from app.services.multimodal.base_provider import MultimodalInferenceProvider
from app.services.multimodal.mock_provider import MockMultimodalProvider

logger = logging.getLogger("cvki.services.multimodal.resolver")


class MultimodalProviderNotFoundError(RuntimeError):
    """Raised when an unapproved or unregistered multimodal provider_id is requested."""
    pass


class MultimodalProviderResolver:
    """
    Controlled registry and factory for approved MultimodalInferenceProvider implementations.
    Strictly forbids dynamic class importing, path traversal, or client-specified code loading.
    """

    def __init__(self):
        self._provider_registry: dict[str, Callable[[], MultimodalInferenceProvider]] = {}
        self._active_instances: dict[str, MultimodalInferenceProvider] = {}
        self._lock = Lock()

        # Register server-side approved providers
        self.register_provider_factory("mock_multimodal_provider", lambda: MockMultimodalProvider())
        self.register_provider_factory("mock_civic_multimodal", lambda: MockMultimodalProvider())

    def register_provider_factory(
        self,
        provider_id: str,
        factory: Callable[[], MultimodalInferenceProvider],
    ) -> None:
        """Registers an authorized provider factory under a normalized identifier."""
        normalized_id = provider_id.strip().lower()
        with self._lock:
            self._provider_registry[normalized_id] = factory

    def resolve_provider(self, provider_id: str) -> MultimodalInferenceProvider:
        """
        Resolves an approved provider instance by ID. Caches active instance for thread safety.
        Rejects arbitrary or unrecognized provider IDs.
        """
        if not provider_id or not isinstance(provider_id, str):
            raise MultimodalProviderNotFoundError("Provider ID must be a non-empty string.")

        normalized_id = provider_id.strip().lower()
        with self._lock:
            if normalized_id in self._active_instances:
                return self._active_instances[normalized_id]

            factory = self._provider_registry.get(normalized_id)
            if factory is None:
                raise MultimodalProviderNotFoundError(
                    f"Multimodal provider '{provider_id}' is not an approved server-side provider. "
                    f"Approved providers: {list(self._provider_registry.keys())}"
                )

            instance = factory()
            self._active_instances[normalized_id] = instance
            logger.info("Instantiated and cached approved multimodal provider: %s", normalized_id)
            return instance

    def reset(self) -> None:
        """Shuts down active provider instances and clears cache."""
        with self._lock:
            for pid, instance in self._active_instances.items():
                try:
                    instance.shutdown()
                except Exception as exc:
                    logger.warning("Error shutting down multimodal provider '%s': %s", pid, exc)
            self._active_instances.clear()


# Shared singleton instance
multimodal_provider_resolver = MultimodalProviderResolver()
