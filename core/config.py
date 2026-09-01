"""Adapter configuration shared across corpora. Lives in core/, not adapters/,
so that signals/ (which must import nothing from adapters/, per the Global
Constraint) can depend on AdapterConfig without depending on any adapter."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterConfig:
    name: str
    required_roles: tuple[str, ...]
