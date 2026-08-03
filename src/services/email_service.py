from __future__ import annotations

from typing import Dict

from models.email_template import EmailTemplate
from repositories.template_repository import TemplateRepository


class EmailService:
    def __init__(self, template_repository: TemplateRepository | None = None) -> None:
        self.templates = template_repository or TemplateRepository()

    def get_template(self, template_name: str) -> EmailTemplate:
        return self.templates.load(template_name)

    def render_rule_based(self, template_name: str, fields: Dict[str, str]) -> Dict[str, str]:
        template = self.get_template(template_name)
        subject = template.subject_template.format(**fields)
        body = template.body_template.format(**fields)
        raw = f"Subject: {subject}\nBody:\n{body}"
        return {"subject": subject, "body": body, "raw": raw}
