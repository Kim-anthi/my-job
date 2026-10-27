/// Job radar - the viewer for the Python worker in `radar/`.
///
/// The worker does the finding and the pushing; this app is for browsing what
/// it found and tracking what you did about it.
library;

import 'package:flutter/material.dart';

import 'data/app_database.dart';
import 'data/job_repository.dart';
import 'ui/job_list_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    final database = await AppDatabase.open();
    final repository = JobRepository(database: database);
    await repository.load();
    // First launch has an empty cache: fill it without making the user hunt
    // for the refresh button.
    if (repository.entries.isEmpty) {
      await repository.refresh();
    }
    runApp(JobRadarApp(repository: repository));
  } catch (error, stack) {
    // Without this the app would just show a blank screen. The usual cause on
    // the web is a missing SQLite wasm bundle, which has a one-line fix.
    debugPrint('Job radar failed to start: $error\n$stack');
    runApp(StartupFailureApp(error: error));
  }
}

/// Shown when the local database cannot be opened at all.
class StartupFailureApp extends StatelessWidget {
  const StartupFailureApp({super.key, required this.error});

  final Object error;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.storage, size: 44),
                  const SizedBox(height: 14),
                  const Text(
                    'Could not open the local database',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'On the web, SQLite needs its WebAssembly binary. Fetch it '
                    'into web/ from the project root, then reload:',
                  ),
                  const SizedBox(height: 8),
                  const SelectableText(
                    'curl -L -o web/sqlite3.wasm '
                    'https://github.com/simolus3/sqlite3.dart/releases/'
                    'download/sqlite3-3.1.2/sqlite3.wasm',
                    style: TextStyle(fontFamily: 'monospace', fontSize: 12),
                  ),
                  const SizedBox(height: 18),
                  SelectableText(
                    '$error',
                    style: const TextStyle(fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class JobRadarApp extends StatelessWidget {
  const JobRadarApp({super.key, required this.repository});

  final JobRepository repository;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Job radar',
      debugShowCheckedModeBanner: false,
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      home: JobListPage(repository: repository),
    );
  }

  ThemeData _theme(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF2563EB),
      brightness: brightness,
    );
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.5)),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
      ),
    );
  }
}
