/// Database setup for everything that is not the web: Android, iOS and, via
/// FFI, the desktop platforms.
library;

import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

Future<void> configureDatabaseFactory() async {
  // Android and iOS ship a SQLite build; the desktops need the FFI one.
  if (Platform.isWindows || Platform.isLinux || Platform.isMacOS) {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  }
}

Future<String> resolveDatabasePath(String name) async {
  return p.join(await getDatabasesPath(), name);
}
