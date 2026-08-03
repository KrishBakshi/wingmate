from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TemplateMeta(BaseModel):
    title: str
    description: str = ""


class EmailTemplate(BaseModel):
    name: str
    meta: TemplateMeta
    variables: List[str] = Field(default_factory=list)
    system_instruction: str
    subject_template: str
    body_template: str
    default_attachment: str | None = None
