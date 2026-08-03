from __future__ import annotations

import base64
import html
import re
from email import encoders
from email import message_from_bytes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH


SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailService:
    EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", flags=re.IGNORECASE)
    SIGNOFF_PATTERN = re.compile(
        r"\b(Best|Regards|Sincerely|Thanks|Thank you|Warm regards|Kind regards),\s+",
        flags=re.IGNORECASE,
    )
    CTA_PATTERN = re.compile(
        r"(?=(Are you open\b|Would you be open\b|Open to\b|Happy to\b|If you are open\b))",
        flags=re.IGNORECASE,
    )
    URL_PATTERN = re.compile(r"(?P<url>(?:https?://|www\.|cal\.com/)\S+)", flags=re.IGNORECASE)

    def __init__(
        self,
        credentials_path: Path | None = None,
        token_path: Path | None = None,
    ) -> None:
        self.credentials_path = Path(credentials_path or GMAIL_CREDENTIALS_PATH)
        self.token_path = Path(token_path or GMAIL_TOKEN_PATH)
        self.service = self._authenticate()

    def _authenticate(self):
        creds: Credentials | None = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
                    if self.token_path.exists():
                        self.token_path.unlink()

            if not creds:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        "Gmail OAuth client credentials file was not found at "
                        f"{self.credentials_path}."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path),
                    SCOPES,
                )
                creds = flow.run_local_server(host="localhost", port=8080)

            self.token_path.write_text(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    @staticmethod
    def _normalize_body(body: str) -> str:
        stripped = body.lstrip()
        if stripped.lower().startswith("body:"):
            return stripped.split(":", 1)[1].lstrip()
        return body

    @classmethod
    def normalize_recipients(cls, recipients: str | None) -> str | None:
        if recipients is None:
            return None

        matches = cls.EMAIL_PATTERN.findall(recipients)
        if not matches:
            return None

        deduped: list[str] = []
        seen: set[str] = set()
        for match in matches:
            normalized = match.strip().strip(";,")
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)

        return ", ".join(deduped) if deduped else None

    @staticmethod
    def _is_html_body(body: str) -> bool:
        return bool(re.search(r"<[a-z][\s\S]*?>", body, flags=re.IGNORECASE))

    @staticmethod
    def _format_plain_email_text(body: str) -> str:
        normalized = re.sub(r"\s+", " ", body).strip()
        if not normalized or "\n" in body:
            return body.strip()

        formatted = normalized

        greeting_match = re.match(r"^((?:Hi|Hello|Dear)\s+[^,]+,)\s+", formatted, flags=re.IGNORECASE)
        greeting = ""
        if greeting_match:
            greeting = greeting_match.group(1).strip()
            formatted = formatted[greeting_match.end() :].strip()

        signoff_match = GmailService.SIGNOFF_PATTERN.search(formatted)
        signoff_block = ""
        if signoff_match:
            signoff_index = signoff_match.start()
            signoff_label = signoff_match.group(1)
            remainder = formatted[signoff_match.end() :].strip()
            name_split = re.match(r"([^,.!?]+?)(?=\s+(?:https?://|www\.|cal\.com/)|$)(.*)", remainder)
            if name_split:
                signer = name_split.group(1).strip()
                trailing = name_split.group(2).strip()
                formatted = formatted[:signoff_index].strip()
                signoff_block = f"{signoff_label},\n{signer}"
                if trailing:
                    signoff_block = f"{signoff_block}\n{trailing}"

        cta_match = GmailService.CTA_PATTERN.search(formatted)
        cta_block = ""
        if cta_match:
            cta_block = formatted[cta_match.start() :].strip()
            formatted = formatted[:cta_match.start()].strip()

        sentence_chunks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", formatted)
        body_paragraphs: list[str] = []
        current_chunk: list[str] = []
        for sentence in sentence_chunks:
            cleaned = sentence.strip()
            if not cleaned:
                continue
            current_chunk.append(cleaned)
            if len(current_chunk) >= 2:
                body_paragraphs.append(" ".join(current_chunk))
                current_chunk = []
        if current_chunk:
            body_paragraphs.append(" ".join(current_chunk))

        if not body_paragraphs and formatted:
            body_paragraphs = [formatted]

        if cta_block:
            cta_block = GmailService.URL_PATTERN.sub(lambda match: f"\n{match.group('url')}", cta_block)

        blocks: list[str] = []
        if greeting:
            blocks.append(greeting)
        blocks.extend(body_paragraphs)
        if cta_block:
            blocks.append(cta_block)
        if signoff_block:
            signoff_block = GmailService.URL_PATTERN.sub(lambda match: f"\n{match.group('url')}", signoff_block)
            blocks.append(signoff_block)

        formatted = "\n\n".join(block.strip() for block in blocks if block.strip())
        formatted = re.sub(r"\n{3,}", "\n\n", formatted)
        return formatted.strip()

    @staticmethod
    def _to_plain_text(body: str) -> str:
        normalized = GmailService._normalize_body(body).replace("\r\n", "\n").replace("\r", "\n")
        if GmailService._is_html_body(normalized):
            text = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
            text = re.sub(r"(?i)</p\s*>", "\n\n", text)
            text = re.sub(r"<[^>]+>", "", text)
            return html.unescape(text).strip()
        return GmailService._format_plain_email_text(normalized)

    @staticmethod
    def _to_html(body: str) -> str:
        normalized = GmailService._normalize_body(body).replace("\r\n", "\n").replace("\r", "\n").strip()
        if GmailService._is_html_body(normalized):
            # If body already has block-level structure, return as-is
            if re.search(r"<(?:p|div|table|ul|ol|h[1-6])\b", normalized, flags=re.IGNORECASE):
                return normalized
            # Inline HTML only (<a>, <br>, etc.) — split on \n\n and wrap in <p> tags
            paragraphs = [seg.strip() for seg in normalized.split("\n\n")]
            rendered: list[str] = []
            for paragraph in paragraphs:
                if not paragraph:
                    continue
                # Only insert <br> before \n when line doesn't already end with <br>
                inner = re.sub(r"(?<!>)\n", "<br>\n", paragraph)
                rendered.append(f"<p>{inner}</p>")
            return "\n".join(rendered) or "<p></p>"

        formatted_text = GmailService._format_plain_email_text(normalized)
        paragraphs = [segment.strip() for segment in formatted_text.split("\n\n")]
        rendered = []
        for paragraph in paragraphs:
            if not paragraph:
                continue
            escaped = html.escape(paragraph).replace("\n", "<br>\n")
            rendered.append(f"<p>{escaped}</p>")
        return "\n".join(rendered) or "<p></p>"

    @staticmethod
    def _build_message(
        to: str | None,
        subject: str,
        body: str,
        attachments: Sequence[str] | None = None,
    ) -> dict[str, str]:
        message = MIMEMultipart()
        normalized_recipients = GmailService.normalize_recipients(to)
        if normalized_recipients:
            message["to"] = normalized_recipients
        message["subject"] = subject
        message_body = MIMEMultipart("alternative")
        message_body.attach(MIMEText(GmailService._to_plain_text(body), "plain"))
        message_body.attach(MIMEText(GmailService._to_html(body), "html"))
        message.attach(message_body)

        for attachment_path in attachments or []:
            path = Path(attachment_path)
            if not path.exists():
                raise FileNotFoundError(f"Attachment not found: {path}")

            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
            message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw_message}

    def create_draft(
        self,
        to: str | None,
        subject: str,
        body: str,
        attachments: Sequence[str] | None = None,
        template: str | None = None,
        allow_unmatched: bool = False,
        allow_sensitive: bool = False,
    ) -> dict[str, object]:
        """Create a Gmail draft, but only if the body conforms to a template and
        discloses no private identity data.

        Drafting is gated on the same checks as sending. A draft is where the
        wording is decided, so catching an off-template body here is the whole
        point — by the time it reaches `send_email` the text has usually already
        been read and approved. Pass `allow_unmatched=True` / `allow_sensitive=
        True` only after the user has answered the returned question.
        """

        try:
            normalized_recipients = self.normalize_recipients(to)
            if to is not None and to.strip() and not normalized_recipients:
                return {
                    "success": False,
                    "error": f"Could not parse recipient email(s) from: {to}",
                    "message": "Failed to create Gmail draft.",
                }

            from services.template_matcher import guard_send

            blocked, match = guard_send(
                body=body,
                template=template,
                allow_unmatched=allow_unmatched,
                action="draft",
            )
            if blocked is not None:
                blocked["normalized_to"] = normalized_recipients
                blocked["subject"] = subject
                return blocked

            from services.identity_service import disclosures_as_dicts, guard_disclosure

            leaked, disclosures = guard_disclosure(
                body=body,
                subject=subject,
                template=template,
                allow_sensitive=allow_sensitive,
            )
            if leaked is not None:
                leaked["normalized_to"] = normalized_recipients
                leaked["subject"] = subject
                leaked["match"] = match.as_dict()
                return leaked

            payload = self._build_message(
                to=normalized_recipients,
                subject=subject,
                body=body,
                attachments=attachments,
            )
            draft = (
                self.service.users()
                .drafts()
                .create(userId="me", body={"message": payload})
                .execute()
            )
            return {
                "success": True,
                "draft_id": draft["id"],
                "normalized_to": normalized_recipients,
                "match": match.as_dict(),
                "drafted_without_template_match": not match.matched,
                "disclosures": disclosures_as_dicts(disclosures),
                "drafted_with_private_data": bool(disclosures),
                "message": "Draft created successfully.",
            }
        except HttpError as exc:
            return {"success": False, "error": str(exc), "message": "Failed to create Gmail draft."}

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Sequence[str] | None = None,
        template: str | None = None,
        allow_unmatched: bool = False,
        allow_sensitive: bool = False,
    ) -> dict[str, object]:
        """Send an email, but only if the body conforms to a template and
        discloses no private identity data.

        Both checks live here rather than in the CLI so that every send path is
        covered — including an inline script that imports this service directly.
        A non-conforming or over-sharing body comes back as a
        `requires_confirmation` refusal instead of being sent; pass
        `allow_unmatched=True` / `allow_sensitive=True` only after the user has
        approved it.
        """

        try:
            normalized_recipients = self.normalize_recipients(to)
            if not normalized_recipients:
                return {
                    "success": False,
                    "error": "Recipient email address is required.",
                    "message": "Failed to send email.",
                }

            from services.template_matcher import guard_send

            blocked, match = guard_send(
                body=body,
                template=template,
                allow_unmatched=allow_unmatched,
            )
            if blocked is not None:
                blocked["normalized_to"] = normalized_recipients
                blocked["subject"] = subject
                return blocked

            from services.identity_service import disclosures_as_dicts, guard_disclosure

            leaked, disclosures = guard_disclosure(
                body=body,
                subject=subject,
                template=template,
                allow_sensitive=allow_sensitive,
            )
            if leaked is not None:
                leaked["normalized_to"] = normalized_recipients
                leaked["subject"] = subject
                leaked["match"] = match.as_dict()
                return leaked

            payload = self._build_message(
                to=normalized_recipients,
                subject=subject,
                body=body,
                attachments=attachments,
            )
            message = self.service.users().messages().send(userId="me", body=payload).execute()
            return {
                "success": True,
                "message_id": message["id"],
                "match": match.as_dict(),
                "sent_without_template_match": not match.matched,
                "disclosures": disclosures_as_dicts(disclosures),
                "sent_with_private_data": bool(disclosures),
                "message": "Email sent successfully.",
            }
        except HttpError as exc:
            return {"success": False, "error": str(exc), "message": "Failed to send email."}

    def update_draft_recipient(
        self,
        draft_id: str,
        to: str,
        template: str | None = None,
        allow_unmatched: bool = False,
        allow_sensitive: bool = False,
    ) -> dict[str, object]:
        """Set the To: header on an existing draft, leaving its wording untouched.

        This exists so that filling in a recipient does not have to go around the
        service to the raw Gmail API (§15.5). The body is pulled back off the
        draft and re-run through the same `guard_send` check `create_draft` uses,
        so a draft whose wording has drifted off-template cannot be quietly made
        sendable by attaching an address to it. Attachments and the existing
        subject are preserved as-is.
        """

        try:
            normalized_recipients = self.normalize_recipients(to)
            if not normalized_recipients:
                return {
                    "success": False,
                    "error": f"Could not parse recipient email(s) from: {to}",
                    "message": "Failed to update draft recipient.",
                }

            draft = (
                self.service.users()
                .drafts()
                .get(userId="me", id=draft_id, format="raw")
                .execute()
            )
            raw = base64.urlsafe_b64decode(draft["message"]["raw"])
            parsed = message_from_bytes(raw)

            body_text = ""
            for part in parsed.walk():
                if part.get_content_type() == "text/html":
                    body_text = part.get_payload(decode=True).decode("utf-8", "ignore")
                    break
            if not body_text:
                for part in parsed.walk():
                    if part.get_content_type() == "text/plain":
                        body_text = part.get_payload(decode=True).decode("utf-8", "ignore")
                        break

            from services.template_matcher import guard_send

            blocked, match = guard_send(
                body=body_text,
                template=template,
                allow_unmatched=allow_unmatched,
                action="draft",
            )
            if blocked is not None:
                blocked["draft_id"] = draft_id
                blocked["normalized_to"] = normalized_recipients
                return blocked

            # Attaching an address is what makes a draft sendable, so the
            # disclosure gate applies here too (§6.2) — an old draft carrying
            # private data must not become sendable by getting a recipient.
            from services.identity_service import guard_disclosure

            leaked, _ = guard_disclosure(
                body=body_text,
                subject=parsed.get("subject", ""),
                template=template,
                allow_sensitive=allow_sensitive,
            )
            if leaked is not None:
                leaked["draft_id"] = draft_id
                leaked["normalized_to"] = normalized_recipients
                return leaked

            del parsed["to"]
            parsed["to"] = normalized_recipients
            payload = {"raw": base64.urlsafe_b64encode(parsed.as_bytes()).decode()}
            updated = (
                self.service.users()
                .drafts()
                .update(userId="me", id=draft_id, body={"message": payload})
                .execute()
            )
            return {
                "success": True,
                "draft_id": updated["id"],
                "normalized_to": normalized_recipients,
                "subject": parsed.get("subject", ""),
                "match": match.as_dict(),
                "updated_without_template_match": not match.matched,
                "message": "Draft recipient updated.",
            }
        except HttpError as exc:
            return {
                "success": False,
                "error": str(exc),
                "message": "Failed to update draft recipient.",
            }

    def list_drafts(self, max_results: int = 10) -> dict[str, object]:
        try:
            response = (
                self.service.users()
                .drafts()
                .list(userId="me", maxResults=max_results)
                .execute()
            )
            drafts = response.get("drafts", [])
            return {"success": True, "count": len(drafts), "drafts": drafts}
        except HttpError as exc:
            return {"success": False, "error": str(exc), "message": "Failed to list drafts."}
