/// Database setup for the web, where SQLite runs as WebAssembly backed by
/// IndexedDB.
///
/// Uses the **no-web-worker** factory, which needs only `web/sqlite3.wasm` and
/// no generated shared worker. The worker variant would be nicer (queries off
/// the UI thread), but its `dart run sqflite_common_ffi_web:setup` step shells
/// out to `webdev`, which fails to locate the Dart SDK on this setup. For a few
/// hundred cached jobs, running SQLite on the main thread is not noticeable.
///
/// `web/sqlite3.wasm` is gitignored, so fetch it after a fresh clone:
///
/// ```
/// curl -L -o web/sqlite3.wasm https://github.com/simolus3/sqlite3.dart/releases/download/sqlite3-3.1.2/sqlite3.wasm
/// ```
library;

import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

Future<void> configureDatabaseFactory() async {
  databaseFactory = databaseFactoryFfiWebNoWebWorker;
}

/// A bare name, not a filesystem path: on the web this is an IndexedDB key.
Future<String> resolveDatabasePath(String name) async => name;
