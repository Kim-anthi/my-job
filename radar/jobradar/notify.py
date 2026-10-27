"""Push channels. Telegram is the default; the console one is for dry runs.

Telegram messages use ``parse_mode=HTML`` rather than MarkdownV2 - escaping
three characters beats escaping eighteen, and job titles are full of brackets
and dashes that MarkdownV2 rejects.
"""
from __future__ import annotations

import html
import logging
import os
import time
from typing import Protocol

from .http import FetchError, post_json
from .models import Job

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_DESCRIPTION = 220


class NotifierError(RuntimeError):
    """A channel is enabled but cannot be used (usually missing credentials)."""


class Notifier(Protocol):
    name: str

    def send_job(self, job: Job) -> bool: ...

    def send_text(self, text: str) -> bool: ...


class ConsoleNotifier:
    """Prints instead of pushing. Used by ``--dry-run`` and local debugging."""

    name = "console"

    def send_job(self, job: Job) -> bool:
        age = job.age_days()
        when = f"{age:.0f}d ago" if age is not None else "date unknown"
        print(f"  [{job.score:>2}] {job.title} - {job.company or 'unknown company'}")
        print(f"       {job.location or 'location n/a'} | {when} | {job.source}")
        print(f"       {job.url}")
        return True

    def send_text(self, text: str) -> bool:
        print(text)
        return True


class TelegramNotifier:
    name = "telegram"

    def __init__(self, token: str, chat_id: str, pause: float = 1.1) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.pause = pause
        self._last_send = 0.0

    @classmethod
    def from_env(cls, settings: dict | None = None) -> "TelegramNotifier | None":
        settings = settings or {}
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            log.warning(
                "telegram disabled: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "(.env locally, repository secrets in CI)"
            )
            return None
        return cls(token, chat_id, pause=float(settings.get("pause_seconds", 1.1)))

    def send_job(self, job: Job) -> bool:
        return self.send_text(format_job(job))

    def send_text(self, text: str) -> bool:
        self._throttle()
        try:
            response = post_json(
                API.format(token=self.token, method="sendMessage"),
                {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except FetchError as exc:
            log.error("telegram send failed: %s", exc)
            return False
        if not response.get("ok"):
            log.error("telegram rejected the message: %s", response)
            return False
        return True

    def check(self) -> str:
        """Verify the token by asking Telegram who the bot is."""
        response = post_json(API.format(token=self.token, method="getMe"), {})
        if not response.get("ok"):
            raise FetchError(f"getMe failed: {response}")
        return str(response["result"].get("username", "unknown"))

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_send
        if self._last_send and elapsed < self.pause:
            time.sleep(self.pause - elapsed)
        self._last_send = time.monotonic()


def format_job(job: Job) -> str:
    """One compact, phone-readable card per job."""
    esc = html.escape
    lines = [f"<b>{esc(job.title)}</b>"]

    subtitle = " · ".join(
        part for part in [esc(job.company), esc(job.location)] if part
    )
    if subtitle:
        lines.append(f"🏢 {subtitle}")
    if job.salary:
        lines.append(f"💰 {esc(job.salary)}")
    if job.tags:
        lines.append(f"🏷 {esc(', '.join(job.tags[:6]))}")

    age = job.age_days()
    meta = [f"🔎 {esc(job.source)}", f"⭐ {job.score}"]
    if age is not None:
        meta.insert(0, "🕐 today" if age < 1 else f"🕐 {age:.0f}d old")
    lines.append(" · ".join(meta))

    if job.description:
        snippet = job.description[:MAX_DESCRIPTION].rstrip()
        if len(job.description) > MAX_DESCRIPTION:
            snippet += "…"
        lines.append(f"\n{esc(snippet)}")

    if job.url:
        lines.append(f'\n<a href="{esc(job.url, quote=True)}">Open posting →</a>')

    return "\n".join(lines)


def build(config: dict, *, dry_run: bool = False) -> list[Notifier]:
    """Assemble the live channels.

    Missing Telegram credentials are a hard error rather than a quiet fallback
    to the console: otherwise a run would mark jobs as notified that never
    reached the phone, and they would never be pushed again.
    """
    notify_config = config.get("notify", {})
    if dry_run:
        return [ConsoleNotifier()]

    notifiers: list[Notifier] = []
    telegram_config = notify_config.get("telegram", {})
    if telegram_config.get("enabled", True):
        telegram = TelegramNotifier.from_env(telegram_config)
        if telegram is not None:
            notifiers.append(telegram)
        elif notify_config.get("allow_console_fallback", False):
            notifiers.append(ConsoleNotifier())
        else:
            raise NotifierError(
                "Telegram is enabled but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are "
                "unset. Put them in radar/.env (locally) or in repository secrets "
                "(CI), or run with --dry-run."
            )

    wants_console = notify_config.get("console", False) or not notifiers
    already_has_console = any(n.name == ConsoleNotifier.name for n in notifiers)
    if wants_console and not already_has_console:
        notifiers.append(ConsoleNotifier())
    return notifiers
