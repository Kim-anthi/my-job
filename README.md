# myjob — personal job radar

Two halves of one tool, tuned for a Flutter/mobile engineer:

| | What it is | Where |
| --- | --- | --- |
| **Worker** | Python. Polls job boards, filters by your keyword rules, remembers what it has seen, pushes new matches to Telegram. Runs free on GitHub Actions. | [radar/](radar/) |
| **App** | Flutter. Browses what the worker found and tracks what you did about it — saved, applied, hidden, notes. | [lib/](lib/) |

```
job boards ──> radar worker ──> Telegram (instant alert)
                     └────────> data/latest.json ──> Flutter app (browse + track)
```

The worker is the part that gets you the job; the app is the part that keeps you
organised. They are only coupled by one file: `radar/data/latest.json`.

## Worker

Zero third-party packages — Python 3.11+ standard library only.

```bash
cd radar
python -m jobradar run --dry-run     # preview what your rules catch
python -m jobradar test-telegram     # after filling in .env
python -m jobradar run
```

Full setup, filter tuning and source configuration: [radar/README.md](radar/README.md).

## App

```bash
flutter pub get
flutter run -d chrome        # or -d <your phone>
```

For **web** runs the SQLite WebAssembly binary must be present once per clone
(it is gitignored, ~720KB):

```bash
curl -L -o web/sqlite3.wasm https://github.com/simolus3/sqlite3.dart/releases/download/sqlite3-3.1.2/sqlite3.wasm
```

Android and iOS need nothing extra. The package's own
`dart run sqflite_common_ffi_web:setup` also fetches it, but on this machine it
fails trying to build an optional shared worker through `webdev` — the app uses
the no-worker factory, so the single file above is all it needs.

It opens on the **bundled sample feed** so there is something to look at before
the worker is live. Point it at the real thing in **Settings → Feed source**:
the raw URL of your committed `radar/data/latest.json`.

To preview a feed you just generated locally:

```bash
cd radar && python -m jobradar export
cd data && python -m http.server 8000
# then set the feed source to http://localhost:8000/latest.json
```

### Why the app has its own database

The feed is read-only and the worker owns it. The app's SQLite database holds
the two things the feed cannot:

- **Your state** — saved, applied, hidden, notes. Kept in a separate
  `job_state` table, so refreshing the feed never overwrites it.
- **A cache** — the list opens instantly offline, and a job you saved stays
  readable after it drops out of the feed's newest-300 window.

### Platform notes on this machine

- **Web (Chrome/Edge)** works now.
- **Android** needs `flutter doctor --android-licenses` accepted, then a
  connected phone or an emulator (`flutter emulators --create`). This is the
  target worth using — it is where the Telegram alerts land too.
- **Windows desktop** needs Visual Studio with the "Desktop development with
  C++" workload, which is not installed. The code supports it (sqflite via
  FFI); only the toolchain is missing.

## Tests

```bash
cd radar && python -m pytest tests -q   # worker: filters, dedup, queue
cd .. && flutter test                   # app: parsing, repository, widgets
```

Both suites run without network access.
