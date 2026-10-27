// Widget tests for the job list: they pump the real pages against an
// in-memory database and a fake feed, so no network or browser is involved.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:myjob/data/app_database.dart';
import 'package:myjob/data/job_repository.dart';
import 'package:myjob/main.dart';
import 'package:myjob/ui/job_list_page.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'job_repository_test.dart' show FakeFeedClient, job;

void main() {
  late AppDatabase database;
  late FakeFeedClient feed;
  late JobRepository repository;

  setUp(() async {
    database = await AppDatabase.open(path: inMemoryDatabasePath);
    feed = FakeFeedClient([
      job('a', title: 'Senior Flutter Engineer', company: 'Acme', score: 10),
      job('b', title: 'Android Developer', company: 'Globex', score: 4),
    ]);
    repository = JobRepository(database: database, feedClient: feed);
    await repository.load();
    await repository.refresh();
  });

  tearDown(() async {
    repository.dispose();
    await database.close();
  });

  Future<void> pumpList(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(home: JobListPage(repository: repository)),
    );
    await tester.pumpAndSettle();
  }

  /// Taps write to a real SQLite database. `pumpAndSettle` runs on fake time
  /// and will not wait for that I/O, so give the write a real moment to land
  /// before asserting on the rebuilt UI.
  Future<void> settleIo(WidgetTester tester) async {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 60)),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('lists the cached jobs with their scores', (tester) async {
    await pumpList(tester);

    expect(find.text('Senior Flutter Engineer'), findsOneWidget);
    expect(find.text('Android Developer'), findsOneWidget);
    expect(find.text('10'), findsOneWidget);
    expect(find.textContaining('Acme'), findsWidgets);
  });

  testWidgets('bookmarking moves a job into Saved', (tester) async {
    await pumpList(tester);
    expect(find.text('Saved 0'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.bookmark_border).first);
    await settleIo(tester);

    expect(find.text('Saved 1'), findsOneWidget);

    await tester.tap(find.text('Saved 1'));
    await tester.pumpAndSettle();

    expect(find.text('Senior Flutter Engineer'), findsOneWidget);
    expect(find.text('Android Developer'), findsNothing);
  });

  testWidgets('search narrows the list', (tester) async {
    await pumpList(tester);

    await tester.enterText(find.byType(TextField).first, 'android');
    await tester.pumpAndSettle();

    expect(find.text('Android Developer'), findsOneWidget);
    expect(find.text('Senior Flutter Engineer'), findsNothing);
  });

  testWidgets('empty filters explain themselves', (tester) async {
    await pumpList(tester);

    await tester.tap(find.text('Applied 0'));
    await tester.pumpAndSettle();

    expect(find.text('No applications yet'), findsOneWidget);
  });

  testWidgets('opening a job shows its detail page', (tester) async {
    await pumpList(tester);

    await tester.tap(find.text('Senior Flutter Engineer'));
    await tester.pumpAndSettle();

    expect(find.text('Mark applied'), findsOneWidget);
    expect(find.text('Match score 10'), findsOneWidget);

    await tester.tap(find.text('Mark applied'));
    await settleIo(tester);

    expect(find.text('Applied'), findsOneWidget);
  });

  testWidgets('a feed error is shown with a retry', (tester) async {
    feed.failure = StateError('boom');
    await repository.refresh();
    await pumpList(tester);

    expect(find.text('Retry'), findsOneWidget);
  });

  // A RenderFlex overflow raises a FlutterError, which fails the test, so
  // simply rendering at these sizes is the assertion.
  for (final size in const [Size(360, 740), Size(390, 844), Size(430, 932)]) {
    testWidgets('list and detail fit a ${size.width.toInt()}px phone',
        (tester) async {
      await tester.binding.setSurfaceSize(size);
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await pumpList(tester);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Senior Flutter Engineer'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Open'), findsOneWidget);
    });
  }

  testWidgets('app boots without throwing', (tester) async {
    await tester.pumpWidget(JobRadarApp(repository: repository));
    await tester.pumpAndSettle();

    expect(find.text('Job radar'), findsOneWidget);
  });
}
