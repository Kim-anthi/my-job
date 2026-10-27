"""Command line interface: ``python -m jobradar <command>``."""
from __future__ import annotations

import argparse
import logging
import sys

from . import config as config_module
from . import filters, notify, runner, sources
from .http import FetchError
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    # Shared options, accepted on either side of the subcommand. SUPPRESS keeps
    # the subparser's unset defaults from clobbering a value given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-c", "--config", default=argparse.SUPPRESS, help="path to config.toml"
    )
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="debug logging",
    )

    parser = argparse.ArgumentParser(
        prog="jobradar",
        parents=[common],
        description="Personal job radar: watch job boards, push new matches to Telegram.",
    )
    subparsers = parser.add_subparsers(dest="command")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return subparsers.add_parser(name, parents=[common], help=help_text)

    run_parser = add("run", "fetch, filter and notify (the default)")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print matches instead of pushing; writes nothing to the database",
    )
    run_parser.add_argument(
        "--max-notifications", type=int, help="override notify.max_per_run for this run"
    )

    list_parser = add("list", "show jobs already in the database")
    list_parser.add_argument("-n", "--limit", type=int, default=20)
    list_parser.add_argument(
        "--status", choices=["new", "notified", "duplicate", "muted"], help="filter by status"
    )

    add("export", "rewrite the JSON feed from the database (no network)")
    add("sources", "list the sources your config enables")
    add("stats", "database counts and the last few runs")
    add("test-telegram", "verify the bot token and send a test message")
    add("explain", "show the compiled include/exclude rules")

    prune_parser = add("prune", "drop old rows from the database")
    prune_parser.add_argument("--days", type=int, help="override storage.prune_after_days")

    return parser


def _force_utf8_streams() -> None:
    """Job titles contain emoji, dashes and accents; a cp1252 Windows console
    would raise UnicodeEncodeError mid-run and lose the rest of the batch."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover - redirected stream
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        settings = config_module.load(getattr(args, "config", None))
    except config_module.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    config_module.load_env()
    command = args.command or "run"

    handlers = {
        "run": _cmd_run,
        "list": _cmd_list,
        "export": _cmd_export,
        "sources": _cmd_sources,
        "stats": _cmd_stats,
        "test-telegram": _cmd_test_telegram,
        "explain": _cmd_explain,
        "prune": _cmd_prune,
    }
    return handlers[command](settings, args)


def _open_store(settings: dict) -> Store:
    return Store(config_module.resolve_path(settings, settings["storage"]["database"]))


def _cmd_run(settings: dict, args: argparse.Namespace) -> int:
    try:
        channels = notify.build(settings, dry_run=args.dry_run)
    except notify.NotifierError as exc:
        print(f"notification error: {exc}", file=sys.stderr)
        return 2

    with _open_store(settings) as store:
        stats = runner.run(
            settings,
            store,
            channels,
            dry_run=args.dry_run,
            max_notifications=args.max_notifications,
        )

        if stats.rejections:
            top = sorted(stats.rejections.items(), key=lambda item: -item[1])[:6]
            logging.info("filtered out: %s", ", ".join(f"{k}={v}" for k, v in top))
        logging.info("run complete: %s", stats.summary())

        for error in stats.errors:
            logging.warning("source error: %s", error)

        if not args.dry_run:
            storage = settings["storage"]
            if storage.get("export_json"):
                target = store.export_json(
                    config_module.resolve_path(settings, storage["export_json"]),
                    limit=int(storage.get("export_limit", 300)),
                )
                logging.info("exported %s", target)

    # A run where every source failed is a failure worth a red CI run.
    if stats.errors and stats.fetched == 0:
        return 1
    return 0


def _cmd_export(settings: dict, _args: argparse.Namespace) -> int:
    """Useful for pointing the Flutter app at a local feed without a full run."""
    storage = settings["storage"]
    if not storage.get("export_json"):
        print("storage.export_json is not set", file=sys.stderr)
        return 2
    with _open_store(settings) as store:
        target = store.export_json(
            config_module.resolve_path(settings, storage["export_json"]),
            limit=int(storage.get("export_limit", 300)),
        )
        print(f"wrote {target} ({store.counts().total} job(s) in the database)")
    return 0


def _cmd_list(settings: dict, args: argparse.Namespace) -> int:
    with _open_store(settings) as store:
        jobs = store.recent(limit=args.limit, status=args.status)
        if not jobs:
            print("nothing stored yet - run `python -m jobradar run` first")
            return 0
        for job in jobs:
            age = job.age_days()
            when = f"{age:.0f}d" if age is not None else "  ?"
            print(f"[{job.score:>2}] {when:>4}  {job.title[:58]:<58} {job.company[:22]}")
            print(f"            {job.url}")
    return 0


def _cmd_sources(settings: dict, _args: argparse.Namespace) -> int:
    live = sources.build(settings)
    if not live:
        print("no sources enabled - set enabled = true on a [sources.*] table")
        return 1
    print(f"{len(live)} source(s) enabled:")
    for source in live:
        detail = {k: v for k, v in source.settings.items() if k not in {"enabled", "name"}}
        print(f"  - {source.name}" + (f"  {detail}" if detail else ""))
    return 0


def _cmd_stats(settings: dict, _args: argparse.Namespace) -> int:
    with _open_store(settings) as store:
        counts = store.counts()
        print(
            f"jobs: {counts.total} total | {counts.notified} notified | "
            f"{counts.pending} queued | {counts.duplicates} cross-source dupes"
        )
        rows = store.db.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 5"
        ).fetchall()
        if rows:
            print("\nrecent runs:")
            for row in rows:
                print(
                    f"  {row['started_at']}  fetched={row['fetched']:<4} "
                    f"matched={row['matched']:<3} new={row['fresh']:<3} "
                    f"notified={row['notified']}"
                    + ("  [errors]" if row["errors"] else "")
                )
    return 0


def _cmd_test_telegram(settings: dict, _args: argparse.Namespace) -> int:
    telegram = notify.TelegramNotifier.from_env(settings.get("notify", {}).get("telegram", {}))
    if telegram is None:
        print(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.\n"
            "  1. message @BotFather on Telegram, /newbot, copy the token\n"
            "  2. send your bot any message, then open\n"
            "     https://api.telegram.org/bot<TOKEN>/getUpdates to read your chat id\n"
            "  3. put both in radar/.env (see .env.example)",
            file=sys.stderr,
        )
        return 2
    try:
        username = telegram.check()
    except FetchError as exc:
        print(f"token rejected: {exc}", file=sys.stderr)
        return 1
    print(f"authenticated as @{username}")
    ok = telegram.send_text(
        "<b>Job radar online ✅</b>\nThis is a test message from your worker."
    )
    print("test message sent" if ok else "send failed - is the chat id right?")
    return 0 if ok else 1


def _cmd_explain(settings: dict, _args: argparse.Namespace) -> int:
    rules = filters.Rules.from_config(settings)
    print(
        f"min_score={rules.min_score}  (title hit={filters.TITLE_HIT_POINTS}, "
        f"distinctive body hit={filters.STRONG_BODY_HIT_POINTS}, "
        f"generic body hit={filters.BODY_HIT_POINTS}, capped at {filters.GENERIC_POINTS_CAP})"
    )
    print(f"require_include_in_title={rules.require_include_in_title}")
    print(f"max_age_days={rules.max_age_days}")
    for label, terms in (
        ("include in title", rules.include_title),
        ("include anywhere (distinctive)", rules.include_strong),
        ("include anywhere (generic)", rules.include_anywhere),
        ("exclude in title", rules.exclude_title),
        ("exclude anywhere", rules.exclude_anywhere),
    ):
        names = ", ".join(term for term, _ in terms) or "(none)"
        print(f"\n{label}:\n  {names}")
    return 0


def _cmd_prune(settings: dict, args: argparse.Namespace) -> int:
    days = args.days or int(settings["storage"].get("prune_after_days", 120))
    with _open_store(settings) as store:
        removed = store.prune(days)
    print(f"removed {removed} job row(s) older than {days} days")
    return 0
