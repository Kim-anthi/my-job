import 'package:flutter_test/flutter_test.dart';
import 'package:myjob/data/feed_client.dart';
import 'package:myjob/models/job.dart';

void main() {
  group('Job.fromFeed', () {
    test('reads a full record from the worker', () {
      final job = Job.fromFeed({
        'key': 'abc123',
        'source': 'remoteok',
        'title': 'Senior Flutter Engineer',
        'company': 'Acme',
        'url': 'https://example.com/1',
        'location': 'Remote',
        'tags': ['flutter', 'dart'],
        'salary': r'$90,000 - $120,000',
        'posted_at': '2026-10-25T09:00:00+00:00',
        'score': 10,
        'reasons': ['title:flutter', 'strong:dart'],
        'summary': 'Build the app.',
        'status': 'notified',
        'first_seen': '2026-10-26T14:08:25+00:00',
      });

      expect(job.key, 'abc123');
      expect(job.title, 'Senior Flutter Engineer');
      expect(job.tags, ['flutter', 'dart']);
      expect(job.score, 10);
      expect(job.postedAt?.toUtc().year, 2026);
      expect(job.status, 'notified');
    });

    test('survives nulls and unexpected types', () {
      final job = Job.fromFeed({
        'key': 'x',
        'title': 'Mobile Engineer',
        'company': null,
        'tags': null,
        'reasons': 'not-a-list',
        'score': '7',
        'posted_at': 'not-a-date',
      });

      expect(job.company, '');
      expect(job.tags, isEmpty);
      expect(job.reasons, isEmpty);
      expect(job.score, 7, reason: 'numeric strings should still parse');
      expect(job.postedAt, isNull);
    });

    test('round-trips through a database row', () {
      final original = Job.fromFeed({
        'key': 'k',
        'title': 'Flutter Dev',
        'company': 'Acme',
        'tags': ['flutter'],
        'reasons': ['title:flutter'],
        'score': 4,
        'posted_at': '2026-10-20T00:00:00Z',
      });

      final restored = Job.fromRow(original.toRow());

      expect(restored.key, original.key);
      expect(restored.title, original.title);
      expect(restored.tags, original.tags);
      expect(restored.reasons, original.reasons);
      expect(restored.score, original.score);
      expect(restored.postedAt, original.postedAt);
    });
  });

  group('parseFeed', () {
    test('parses the worker payload', () {
      final payload = parseFeed('''
        {"generated_at": "2026-10-26T14:08:37+00:00", "count": 1,
         "jobs": [{"key": "a", "title": "Flutter Engineer", "company": "Acme"}]}
      ''');

      expect(payload.jobs, hasLength(1));
      expect(payload.generatedAt?.toUtc().day, 26);
    });

    test('drops records with no key or title', () {
      final payload = parseFeed(
        '{"jobs": [{"key": "", "title": "No key"}, '
        '{"key": "b", "title": ""}, {"key": "c", "title": "Keep me"}]}',
      );

      expect(payload.jobs.map((job) => job.key), ['c']);
    });

    test('rejects malformed payloads with a readable message', () {
      expect(() => parseFeed('not json'), throwsA(isA<FeedException>()));
      expect(() => parseFeed('[]'), throwsA(isA<FeedException>()));
      expect(() => parseFeed('{"count": 0}'), throwsA(isA<FeedException>()));
    });
  });

  group('formatAge', () {
    test('describes recent and old moments', () {
      final now = DateTime.now().toUtc();
      expect(formatAge(now), 'today');
      expect(formatAge(now.subtract(const Duration(days: 1, hours: 1))),
          'yesterday');
      expect(formatAge(now.subtract(const Duration(days: 4))), '4d ago');
      expect(formatAge(now.subtract(const Duration(days: 21))), '3w ago');
      expect(formatAge(now.subtract(const Duration(days: 90))), '3mo ago');
      expect(formatAge(null), 'undated');
    });
  });
}
