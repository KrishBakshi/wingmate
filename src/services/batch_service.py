from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from typing import Callable

import pandas as pd

from services.email_service import EmailService
from services.gmail_service import GmailService


class BatchService:
    def __init__(
        self,
        email_service: EmailService | None = None,
        gmail_service: GmailService | None = None,
    ) -> None:
        self.email_service = email_service or EmailService()
        self.gmail_service = gmail_service
        self._template_cache: dict[str, Any] = {}
        self._render_cache: dict[str, dict[str, str]] = {}

    @staticmethod
    def read_tabular(file_path: str | Path) -> dict[str, Any]:
        try:
            path = Path(file_path)
            suffix = path.suffix.lower()

            if suffix == ".csv":
                dataframe = pd.read_csv(path)
                file_kind = "CSV"
            else:
                dataframe = pd.read_excel(path)
                file_kind = "Excel"

            records = dataframe.to_dict("records")
            return {
                "success": True,
                "data": records,
                "columns": list(dataframe.columns),
                "row_count": len(records),
                "message": f"Successfully read {len(records)} row(s) from {file_kind} file.",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "message": f"Error reading uploaded file: {exc}",
            }

    def validate_excel_columns(
        self,
        excel_columns: list[str],
        template_name: str,
        email_column: str = "email",
    ) -> dict[str, Any]:
        template = self._get_template(template_name)
        required_fields = set(template.variables)
        excel_cols = set(excel_columns)

        missing_fields = required_fields - excel_cols
        extra_fields = excel_cols - required_fields
        if email_column in extra_fields:
            extra_fields.remove(email_column)

        if missing_fields:
            return {
                "success": False,
                "error": f"Uploaded file is missing required columns: {', '.join(sorted(missing_fields))}",
                "missing_fields": sorted(missing_fields),
                "extra_fields": sorted(extra_fields),
            }

        return {
            "success": True,
            "message": "Uploaded file columns match template fields.",
            "required_fields": sorted(required_fields),
            "extra_fields": sorted(extra_fields),
            "email_column_present": email_column in excel_cols,
        }

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return pd.isna(value) or value == ""

    def _extract_template_fields(
        self,
        row: dict[str, Any],
        template_name: str,
        email_column: str,
    ) -> dict[str, Any]:
        template = self._get_template(template_name)
        template_fields: dict[str, Any] = {}
        for key in template.variables:
            value = row.get(key)
            if not self._is_empty(value):
                template_fields[key] = value
        return template_fields

    def _get_template(self, template_name: str):
        if template_name not in self._template_cache:
            self._template_cache[template_name] = self.email_service.get_template(template_name)
        return self._template_cache[template_name]

    @staticmethod
    def _render_cache_key(
        template_name: str,
        template_fields: dict[str, Any],
    ) -> str:
        return json.dumps(
            {
                "template_name": template_name,
                "template_fields": template_fields,
            },
            sort_keys=True,
            default=str,
        )

    def _render_email(
        self,
        template_name: str,
        template_fields: dict[str, Any],
    ) -> dict[str, str]:
        cache_key = self._render_cache_key(template_name, template_fields)
        if cache_key not in self._render_cache:
            self._render_cache[cache_key] = self.email_service.render_rule_based(
                template_name, template_fields
            )
        return self._render_cache[cache_key]

    def process_batch(
        self,
        excel_path: str | Path,
        template_name: str,
        email_column: str = "email",
        attachments: list[str] | None = None,
        delay_seconds: float = 0.25,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        excel_result = self.read_tabular(excel_path)
        if not excel_result["success"]:
            return excel_result

        records = excel_result["data"]
        columns = excel_result["columns"]
        validation = self.validate_excel_columns(columns, template_name, email_column=email_column)
        if not validation["success"]:
            return validation

        if self.gmail_service is None:
            return {
                "success": False,
                "error": "Gmail service is not initialized.",
                "message": "Authenticate with Gmail before creating drafts.",
            }

        results: list[dict[str, Any]] = []
        successful = 0
        failed = 0
        email_column_present = validation["email_column_present"]

        for idx, row in enumerate(records, start=1):
            try:
                raw_recipient = None
                recipient = None
                if email_column_present:
                    raw_recipient = row.get(email_column)
                    if not self._is_empty(raw_recipient):
                        raw_recipient = str(raw_recipient).strip()
                        recipient = GmailService.normalize_recipients(raw_recipient)
                        if not recipient:
                            row_result = {
                                "row": idx,
                                "recipient": raw_recipient,
                                "success": False,
                                "error": f"Could not parse recipient email(s) from: {raw_recipient}",
                            }
                            results.append(row_result)
                            failed += 1
                            if progress_callback is not None:
                                progress_callback(
                                    {
                                        "current": idx,
                                        "total": len(records),
                                        "successful": successful,
                                        "failed": failed,
                                        "item": row_result,
                                    }
                                )
                            if delay_seconds > 0 and idx < len(records):
                                time.sleep(delay_seconds)
                            continue

                template_fields = self._extract_template_fields(row, template_name, email_column)
                rendered = self._render_email(template_name, template_fields)
                draft_result = self.gmail_service.create_draft(
                    to=raw_recipient if raw_recipient else None,
                    subject=rendered["subject"],
                    body=rendered["body"],
                    attachments=attachments,
                )

                if draft_result["success"]:
                    row_result = {
                        "row": idx,
                        "recipient": draft_result.get("normalized_to") or recipient or "",
                        "success": True,
                        "draft_id": draft_result["draft_id"],
                        "message": "Draft created successfully.",
                    }
                    results.append(row_result)
                    successful += 1
                else:
                    row_result = {
                        "row": idx,
                        "recipient": recipient or "",
                        "success": False,
                        "error": draft_result.get("error", draft_result.get("message", "Unknown error")),
                    }
                    results.append(row_result)
                    failed += 1

                if progress_callback is not None:
                    progress_callback(
                        {
                            "current": idx,
                            "total": len(records),
                            "successful": successful,
                            "failed": failed,
                            "item": row_result,
                        }
                    )

                if delay_seconds > 0 and idx < len(records):
                    time.sleep(delay_seconds)
            except Exception as exc:
                row_result = {
                    "row": idx,
                    "recipient": str(row.get(email_column, "") or ""),
                    "success": False,
                    "error": str(exc),
                }
                results.append(row_result)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "current": idx,
                            "total": len(records),
                            "successful": successful,
                            "failed": failed + 1,
                            "item": row_result,
                        }
                )
                failed += 1

        return {
            "success": True,
            "total_rows": len(records),
            "successful": successful,
            "failed": failed,
            "results": results,
            "message": f"Processed {len(records)} row(s): {successful} successful, {failed} failed.",
        }

    def preview_batch(
        self,
        excel_path: str | Path,
        template_name: str,
        email_column: str = "email",
        max_preview: int = 3,
    ) -> dict[str, Any]:
        excel_result = self.read_tabular(excel_path)
        if not excel_result["success"]:
            return excel_result

        records = excel_result["data"][:max_preview]
        columns = excel_result["columns"]
        validation = self.validate_excel_columns(columns, template_name, email_column=email_column)
        if not validation["success"]:
            return validation

        previews: list[dict[str, Any]] = []
        email_column_present = validation["email_column_present"]

        for idx, row in enumerate(records, start=1):
            try:
                recipient = ""
                if email_column_present:
                    raw_recipient = row.get(email_column)
                    if not self._is_empty(raw_recipient):
                        recipient = GmailService.normalize_recipients(str(raw_recipient)) or ""

                template_fields = self._extract_template_fields(row, template_name, email_column)
                rendered = self._render_email(template_name, template_fields)
                previews.append(
                    {
                        "row": idx,
                        "recipient": recipient,
                        "subject": rendered["subject"],
                        "body": rendered["body"],
                        "fields": template_fields,
                    }
                )
            except Exception as exc:
                previews.append(
                    {
                        "row": idx,
                        "recipient": GmailService.normalize_recipients(str(row.get(email_column, "") or "")) or "",
                        "error": str(exc),
                    }
                )

        return {
            "success": True,
            "previews": previews,
            "total_rows": excel_result["row_count"],
            "showing": len(previews),
            "message": f"Showing {len(previews)} of {excel_result['row_count']} row(s).",
        }

    def generate_sample_excel(
        self,
        template_name: str,
        output_path: str | Path,
        email_column: str = "email",
    ) -> dict[str, Any]:
        try:
            template = self._get_template(template_name)
            sample_data = {
                field: [f"sample_{field}_1", f"sample_{field}_2"]
                for field in template.variables
            }
            sample_data[email_column] = ["recipient1@example.com", ""]
            dataframe = pd.DataFrame(sample_data)
            dataframe.to_excel(output_path, index=False)
            return {
                "success": True,
                "file_path": str(output_path),
                "message": f"Sample Excel file created at {output_path}.",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
