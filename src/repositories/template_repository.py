from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from config.settings import TEMPLATES_DIR
from models.email_template import EmailTemplate
from utils.placeholder import extract_placeholders


class TemplateRepository:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = Path(template_dir or TEMPLATES_DIR)
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def list_template_names(self) -> List[str]:
        return sorted(path.stem for path in self.template_dir.glob("*.yaml"))

    def load(self, template_name: str) -> EmailTemplate:
        path = self.template_dir / f"{template_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            payload = yaml.safe_load(file)
        return EmailTemplate.model_validate(payload)

    def save(self, template: EmailTemplate) -> Path:
        path = self.template_dir / f"{template.name}.yaml"
        with path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(template.model_dump(), file, sort_keys=False, allow_unicode=False)
        return path

    def validate_template(self, template: EmailTemplate) -> List[str]:
        errors: List[str] = []
        expected = set(template.variables)

        subject_fields = extract_placeholders(template.subject_template)
        body_fields = extract_placeholders(template.body_template)

        missing_from_def = (subject_fields | body_fields) - expected
        if missing_from_def:
            errors.append(
                "Variables used but not declared in 'variables': "
                + ", ".join(sorted(missing_from_def))
            )

        unused_declared = expected - (subject_fields | body_fields)
        if unused_declared:
            errors.append(
                "Variables declared but unused in subject/body: "
                + ", ".join(sorted(unused_declared))
            )

        return errors
