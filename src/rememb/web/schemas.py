"""Request models for the rememb web API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WriteRequest(BaseModel):
    content: str
    section: str
    tags: list[str] = []


class EditRequest(BaseModel):
    content: str | None = None
    section: str | None = None
    tags: list[str] | None = None


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any]


class ConsolidateRequest(BaseModel):
    section: str | None = None
