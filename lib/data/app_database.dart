/// The app's local store.
///
/// Why a database at all, when the worker already publishes a JSON feed? Two
/// reasons the feed cannot cover:
///
/// * **Your state.** Saved, applied, hidden and notes are yours, not the
///   worker's. They live in `job_state`, a separate table, so refreshing the
///   feed can never overwrite them - an upsert into `jobs` leaves `job_state`
///   untouched.
/// * **Offline.** The feed keeps only the newest few hundred postings and needs
///   a network. Once cached locally, the list opens instantly and a job you
///   saved stays readable after it drops out of the feed.
library;

import 'package:sqflite/sqflite.dart';

import '../models/job.dart';
import 'db_setup.dart';

const String kDatabaseName = 'jobradar.db';
const int kSchemaVersion = 1;

class AppDatabase {
  AppDatabase(this._db);

  final Database _db;

  /// Opens the local database, configuring the right SQLite backend first.
  static Future<AppDatabase> open({String? path}) async {
    await configureDatabaseFactory();
    final location = path ?? await resolveDatabasePath(kDatabaseName);
    final db = await openDatabase(
      location,
      version: kSchemaVersion,
      onCreate: (db, version) async {
        final batch = db.batch();
        batch.execute('''
          CREATE TABLE jobs (
            key        TEXT PRIMARY KEY,
            source     TEXT,
            title      TEXT NOT NULL,
            company    TEXT,
            url        TEXT,
            location   TEXT,
            salary     TEXT,
            summary    TEXT,
            status     TEXT,
            tags       TEXT,
            reasons    TEXT,
            score      INTEGER NOT NULL DEFAULT 0,
            posted_at  TEXT,
            first_seen TEXT
          )
        ''');
        // No foreign key to jobs on purpose: an INSERT OR REPLACE of a job row
        // would cascade and delete the state attached to it.
        batch.execute('''
          CREATE TABLE job_state (
            key        TEXT PRIMARY KEY,
            saved      INTEGER NOT NULL DEFAULT 0,
            applied    INTEGER NOT NULL DEFAULT 0,
            hidden     INTEGER NOT NULL DEFAULT 0,
            note       TEXT,
            updated_at TEXT
          )
        ''');
        batch.execute('''
          CREATE TABLE settings (
            name  TEXT PRIMARY KEY,
            value TEXT
          )
        ''');
        batch.execute('CREATE INDEX idx_jobs_first_seen ON jobs(first_seen)');
        batch.execute('CREATE INDEX idx_jobs_score ON jobs(score)');
        await batch.commit(noResult: true);
      },
    );
    return AppDatabase(db);
  }

  Future<void> close() => _db.close();

  /// Writes the feed in, keeping whatever state you had attached to each job.
  Future<int> upsertJobs(Iterable<Job> jobs) async {
    final batch = _db.batch();
    for (final job in jobs) {
      batch.insert(
        'jobs',
        job.toRow(),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    }
    final results = await batch.commit(noResult: false);
    return results.length;
  }

  /// Every cached job with your state attached, newest first.
  Future<List<JobEntry>> entries() async {
    final rows = await _db.rawQuery('''
      SELECT j.*,
             s.saved, s.applied, s.hidden, s.note, s.updated_at
      FROM jobs j
      LEFT JOIN job_state s ON s.key = j.key
      ORDER BY j.first_seen DESC, j.score DESC
    ''');
    return rows
        .map(
          (row) => JobEntry(
            job: Job.fromRow(row),
            state: row['updated_at'] == null
                ? JobState.none
                : JobState.fromRow(row),
          ),
        )
        .toList(growable: false);
  }

  Future<void> saveState(String key, JobState state) async {
    await _db.insert(
      'job_state',
      state.toRow(key),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<String?> setting(String name) async {
    final rows = await _db.query(
      'settings',
      columns: ['value'],
      where: 'name = ?',
      whereArgs: [name],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return rows.first['value'] as String?;
  }

  Future<void> setSetting(String name, String value) async {
    await _db.insert('settings', {
      'name': name,
      'value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Drops cached jobs you never interacted with. Saved, applied, hidden and
  /// annotated jobs are kept, which is the point of storing state separately.
  Future<int> clearUntouchedJobs() async {
    return _db.rawDelete('''
      DELETE FROM jobs WHERE key NOT IN (
        SELECT key FROM job_state
        WHERE saved = 1 OR applied = 1 OR hidden = 1
           OR (note IS NOT NULL AND note <> '')
      )
    ''');
  }
}
