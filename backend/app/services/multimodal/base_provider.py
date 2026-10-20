"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal Provider Abstraction SPI

Defines the framework-agnostic Multimodal Inference Provider Service Provider Interface (SPI).
Decouples high-level civic intelligence from specific model engines (local LLMs, VLMs, or
future multi-modal architectures).

Contains NO vendor-specific SDK imports (no openai, anthropic, google-generativeai, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.services.multimodal.contracts import (
    MultimodalInput,
    MultimodalTaskType,
    StandardMultimodalResult,
)


class MultimodalProviderDescriptor(BaseModel):
    """
    Metadata descriptor identifying a multimodal provider implementation.
    Specifies provider identity, model artifact version, tasks, and declared capabilities.
    """
    provider_id: str = Field(min_length=1, description="Unique identifier for the provider implementation")
    model_id: str = Field(min_length=1, description="Identifier of the model instance or family")
    model_version: str = Field(min_length=1, description="Model version string")
    supported_tasks: list[MultimodalTaskType | str] = Field(
        default_factory=list,
        description="List of supported multimodal task categories",
    )
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en"],
        description="List of supported language codes (e.g. en, hi, hinglish)",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Declared capability tokens (e.g. text_reasoning, image_understanding)",
    )
    is_deterministic: bool = Field(
        default=True,
        description="Whether the provider operates with deterministic outputs",
    )
    production_ready: bool = Field(
        default=False,
        description="Flag indicating readiness for production traffic",
    )
    model_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 cryptographic hash of model weights or system configuration",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible provider metadata without credentials or filesystem paths",
    )


class MultimodalInferenceProvider(ABC):
    """
    Abstract Service Provider Interface (SPI) for Multimodal Inference Engines.
    All multimodal adapters (M9.1 mock, future local/remote reasoning engines)
    must strictly conform to this interface.
    """

    @property
    @abstractmethod
    def descriptor(self) -> MultimodalProviderDescriptor:
        """Returns the metadata descriptor identifying this provider and its capabilities."""
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Returns True if the provider is initialized and ready to serve inference requests."""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initializes the provider, verifies resources, and sets up execution state.
        Returns True on success, False otherwise.
        """
        pass

    @abstractmethod
    def infer(self, input_data: MultimodalInput) -> StandardMultimodalResult:
        """
        Executes multimodal analysis on the provided input and returns a validated StandardMultimodalResult.
        Must be thread-safe.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Releases all cached provider resources cleanly."""
        pass
