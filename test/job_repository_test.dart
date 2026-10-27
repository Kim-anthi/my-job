// Repository tests against a real in-memory SQLite database.
//
// The one that matters most is `refresh keeps your state`: the whole reason
// jobs and state live in separate tables is that pulling a new feed must not
// erase what you saved or applied to.
import 'package:flutter_test/flutter_test.dart';
import 'package:myjob/data/app_database.dart';
import 'package:myjob/data/feed_client.dart';
import 'package:myjob/data/job_repository.dart';
import 'package:myjob/models/job.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class FakeFeedClient implements FeedClient {
  FakeFeedClient(this.jobs);

  List<Job> jobs;
  Object? failure;
  int calls = 0;
  String? lastSource;

  @override
  Future<FeedPayload> fetch(String source) async {
    calls++;
    lastSource = source;
    final failure = this.failure;
    if (failure != null) throw failure;
    return FeedPayload(jobs: jobs, generatedAt: DateTime.utc(2026, 10, 26));
  }
}

Job job(
  String key, {
  String title = 'Flutter Engineer',
  String company = 'Acme',
  int score = 4,
  List<String> tags = const ['flutter'],
  int daysAgo = 1,
}) {
  final seen = DateTime.utc(2026, 10, 26).subtract(Duration(days: daysAgo));
  return Job(
    key: key,
    source: 'test',
    title: title,
    company: company,
    url: 'https://example.com/$key',
    location: 'Remote',
    tags: tags,
    score: score,
    postedAt: seen,
    firstSeen: seen,
  );
}

void main() {
  late AppDatabase database;
  late FakeFeedClient feed;
  late JobRepository repository;

  setUp(() async {
    database = await AppDatabase.open(path: inMemoryDatabasePath);
    feed = FakeFeedClient([job('a'), job('b', title: 'iOS Developer')]);
    repository = JobRepository(database: database, feedClient: feed);
    await repository.load();
  });

  tearDown(() async {
    repository.dispose();
    await database.close();
  });

  test('refresh caches the feed', () async {
    await repository.refresh();

    expect(repository.entries, hasLength(2));
    expect(repository.error, isNull);
    expect(repository.lastRefresh, isNotNull);
  });

  test('refresh keeps your state', () async {
    await repository.refresh();
    await repository.toggleSaved('a');
    await repository.setNote('a', 'emailed the recruiter');

    // The same job comes back in a later feed, with an updated score.
    feed.jobs = [job('a', score: 9), job('b', title: 'iOS Developer')];
    await repository.refresh();

    final entry = repository.entries.firstWhere((item) => item.key == 'a');
    expect(entry.state.saved, isTrue, reason: 'state must survive a refresh');
    expect(entry.state.note, 'emailed the recruiter');
    expect(entry.job.score, 9, reason: 'feed data should still update');
  });

  test('marking applied also saves the job', () async {
    await repository.refresh();
    await repository.toggleApplied('b');

    final entry = repository.entries.firstWhere((item) => item.key == 'b');
    expect(entry.state.applied, isTrue);
    expect(entry.state.saved, isTrue);
    expect(repository.count(JobFilter.applied), 1);
  });

  test('hidden jobs leave the inbox', () async {
    await repository.refresh();
    expect(repository.count(JobFilter.inbox), 2);

    await repository.toggleHidden('a');

    expect(repository.count(JobFilter.inbox), 1);
    expect(repository.count(JobFilter.hidden), 1);

    await repository.toggleHidden('a');
    expect(repository.count(JobFilter.inbox), 2);
  });

  test('search matches title, company and tags', () async {
    feed.jobs = [
      job('a', title: 'Flutter Engineer', company: 'Acme'),
      job('b', title: 'Backend Dev', company: 'Globex', tags: ['go']),
    ];
    await repository.refresh();

    expect(repository.view(filter: JobFilter.inbox, query: 'flutter'),
        hasLength(1));
    expect(
        repository.view(filter: JobFilter.inbox, query: 'globex'), hasLength(1));
    expect(repository.view(filter: JobFilter.inbox, query: 'go'), hasLength(1));
    expect(repository.view(filter: JobFilter.inbox, query: 'rust'), isEmpty);
  });

  test('sorts by newest or by best match', () async {
    feed.jobs = [
      job('old-strong', score: 10, daysAgo: 9),
      job('new-weak', score: 4, daysAgo: 1),
    ];
    await repository.refresh();

    expect(
      repository.view(filter: JobFilter.inbox, sort: JobSort.newest).first.key,
      'new-weak',
    );
    expect(
      repository
          .view(filter: JobFilter.inbox, sort: JobSort.bestMatch)
          .first
          .key,
      'old-strong',
    );
  });

  test('feed failures surface as an error, not a crash', () async {
    feed.failure = FeedException('Not found (404).');

    await repository.refresh();

    expect(repository.error, contains('404'));
    expect(repository.busy, isFalse);
    expect(repository.entries, isEmpty);
  });

  test('feed source is persisted and triggers a refresh', () async {
    await repository.setFeedSource('https://example.com/latest.json');

    expect(feed.lastSource, 'https://example.com/latest.json');
    expect(await database.setting(kFeedSourceSetting),
        'https://example.com/latest.json');

    // A fresh repository over the same database remembers it.
    final reopened = JobRepository(database: database, feedClient: feed);
    await reopened.load();
    expect(reopened.feedSource, 'https://example.com/latest.json');
    expect(reopened.usingSampleFeed, isFalse);
    reopened.dispose();
  });

  test('clearing the cache keeps jobs you touched', () async {
    await repository.refresh();
    await repository.toggleSaved('a');

    final removed = await database.clearUntouchedJobs();
    await repository.load();

    expect(removed, 1);
    expect(repository.entries.map((entry) => entry.key), ['a']);
  });
}
