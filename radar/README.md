# Job radar

A personal job watcher: it polls a handful of job boards, keeps only the
postings that match your Flutter/mobile keyword rules, remembers what it has
already seen, and pushes new matches to Telegram.

Runs on GitHub Actions four times a day for free. No server, no database
service, **no third-party Python packages** — Python 3.11+ standard library
only.

```
boards ──> fetch ──> filter (keywords + score) ──> dedup (SQLite) ──> Telegram
                                                          └──> data/latest.json
```

## Quick start

```bash
cd radar

# 1. See what your rules would catch right now - sends nothing, writes nothing.
python -m jobradar run --dry-run

# 2. Set up Telegram (see below), then check the connection.
python -m jobradar test-telegram

# 3. For real.
python -m jobradar run
```

### Telegram in three steps

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
   follow the prompts, copy the token it gives you.
2. Send your new bot any message (it cannot message you first), then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy
   `result[0].message.chat.id`.
3. `cp .env.example .env` and fill in both values.

`.env` is gitignored. For GitHub Actions, add the same two values as repository
secrets instead: **Settings → Secrets and variables → Actions**, named
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Commands

| Command | What it does |
| --- | --- |
| `run` | Fetch, filter, notify. Add `--dry-run` to preview safely. |
| `run --max-notifications 3` | Override the per-run message cap once. |
| `explain` | Print the compiled keyword rules and scoring. |
| `list -n 30 [--status new]` | Show what is in the database. |
| `sources` | List the sources your config enables. |
| `stats` | Counts plus the last five runs. |
| `test-telegram` | Verify the bot token and send a test message. |
| `export` | Rewrite `data/latest.json` from the database (no network, no pushes). |
| `prune --days 90` | Drop old rows. |

## Tuning the filters

Everything lives in [`config.toml`](config.toml). Scoring works like this:

| Signal | Points |
| --- | --- |
| Include keyword in the **title** | 4 |
| **Distinctive** keyword anywhere (`flutter`, `dart`, `react native`) | 3 |
| **Generic** keyword anywhere (`android`, `ios`, `firebase`) | 1, capped at 2 total |

A job needs `match.min_score` (default 4) to qualify. So a title match passes,
two distinctive body mentions pass, and a platform role that merely lists
"Android, iOS, Kotlin, Firebase" in its description does not — the generic cap
is there so vocabulary alone can never qualify a job.

Exclusions are split on purpose:

- `exclude.title_any` — matched against the **title only**. "Java backend" in a
  description is normal for a mobile role ("you will work with our Java backend
  team"); in the title it means the job is not for you.
- `exclude.anywhere_any` — matched against the whole posting. One hit rejects
  the job, so keep this list short and unambiguous.

After editing, check your work: `python -m jobradar explain`, then
`python -m jobradar run --dry-run`.

## Sources

Enabled by default: **RemoteOK**, **Remotive** (their free API caps responses at
10 jobs), **Arbeitnow**, and **We Work Remotely** via RSS. A live run pulls
roughly 700 postings.

To watch a specific company, find its board token in the careers page URL and
add a block:

```toml
[[sources.greenhouse]]   # boards.greenhouse.io/<board>
board = "monzo"
company = "Monzo"
enabled = true

[[sources.lever]]        # jobs.lever.co/<company>
company = "plaid"
enabled = true

[[sources.rss]]          # any RSS or Atom job feed
name = "my-feed"
url = "https://example.com/jobs.rss"
title_format = "company: title"   # when the feed packs both into the title
```

A source that errors is logged and skipped — one dead board never sinks a run.

## Deduplication

Two keys per job, so the same posting never pings twice:

- `key` — identity within one board.
- `alt_key` — company plus normalised title, which catches the same job
  arriving from RemoteOK *and* We Work Remotely.

A match is written to SQLite the moment it is found, with `status='new'`, and
only flipped to `notified` once the push actually succeeded. So a Telegram
outage — or hitting `notify.max_per_run` — leaves jobs queued for the next run
instead of losing them. That is also why the first real run only sends 12
messages rather than everything a board has ever posted.

## GitHub Actions

[`.github/workflows/job-radar.yml`](../.github/workflows/job-radar.yml) runs the
worker at 07:00, 12:00, 16:00 and 20:00 EAT. Add the two Telegram secrets, push,
and it starts on the next slot (or run it by hand from the Actions tab — the
`dry_run` input lets you test it without sending anything).

The SQLite file lives in the Actions cache rather than the repo, so the repo
does not grow by a binary database four times a day. If the cache is ever
evicted you get one batch of repeat alerts, capped at `notify.max_per_run`.

`data/latest.json` *is* committed on each run: it is text, it diffs cleanly, and
it is the feed the Flutter app can read.

Note: GitHub pauses scheduled workflows in repositories with no commit activity
for 60 days. The feed commit each run keeps it alive on its own.

## Feeding the Flutter app

Each run writes `data/latest.json`:

```json
{
  "generated_at": "2026-10-26T14:05:31+00:00",
  "count": 42,
  "jobs": [
    {
      "key": "8f2c…", "source": "remoteok", "title": "Senior Flutter Engineer",
      "company": "Acme", "url": "https://…", "location": "Remote",
      "tags": ["flutter", "dart"], "salary": "", "posted_at": "2026-10-25T09:00:00+00:00",
      "score": 10, "reasons": ["title:flutter", "strong:dart"],
      "summary": "Build and own our Flutter app…",
      "status": "notified", "first_seen": "2026-10-26T14:05:31+00:00",
      "notified_at": "2026-10-26T14:05:33+00:00"
    }
  ]
}
```

Point the app at the raw GitHub URL for that file and you have a read-only feed
with no backend to host. The Flutter app in [`../lib`](../lib) does exactly
that - see the [root README](../README.md).

To preview a feed locally without waiting for a scheduled run:

```bash
python -m jobradar export          # rebuild latest.json from the database
cd data && python -m http.server 8000
# then set the app's feed source to http://localhost:8000/latest.json
```

`summary` is the description trimmed to 600 characters - enough for the app's
detail view without bloating a file that gets committed four times a day.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The suite covers the filter rules (including the false-positive traps: `dart`
must not match "Dartmouth", `ios` must not match "bios") and the dedup/queue
behaviour, all without network access.
