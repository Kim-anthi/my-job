/// Reads the worker's `latest.json`, either over HTTP or from the bundled
/// sample.
///
/// Deliberately no local-file support: `dart:io` does not exist on the web, and
/// a conditional import for a path the phone cannot reach anyway is not worth
/// it. To preview a freshly generated feed, serve it:
///
/// ```
/// cd radar/data && python -m http.server 8000
/// ```
///
/// then point the app at `http://localhost:8000/latest.json`.
library;

import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;

import '../models/job.dart';

/// The sentinel feed source that loads the asset shipped with the app.
const String kSampleFeedSource = 'sample';
const String kSampleAssetPath = 'assets/sample_feed.json';

class FeedException implements Exception {
  FeedException(this.message);

  final String message;

  @override
  String toString() => message;
}

class FeedPayload {
  const FeedPayload({required this.jobs, this.generatedAt});

  final List<Job> jobs;
  final DateTime? generatedAt;
}

abstract class FeedClient {
  Future<FeedPayload> fetch(String source);
}

class HttpFeedClient implements FeedClient {
  HttpFeedClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  @override
  Future<FeedPayload> fetch(String source) async {
    final body = source == kSampleFeedSource
        ? await rootBundle.loadString(kSampleAssetPath)
        : await _get(source);
    return parseFeed(body);
  }

  Future<String> _get(String source) async {
    final uri = Uri.tryParse(source);
    if (uri == null || !uri.isScheme('http') && !uri.isScheme('https')) {
      throw FeedException(
        'Feed source must be an http(s) URL, or "$kSampleFeedSource".',
      );
    }
    try {
      final response = await _client.get(uri);
      if (response.statusCode == 404) {
        throw FeedException(
          'Not found (404). Has the worker committed data/latest.json yet?',
        );
      }
      if (response.statusCode != 200) {
        throw FeedException('Feed returned HTTP ${response.statusCode}.');
      }
      // Explicit UTF-8: job descriptions carry accents and emoji, and
      // response.body would fall back to latin-1 without a charset header.
      return utf8.decode(response.bodyBytes);
    } on FeedException {
      rethrow;
    } catch (error) {
      throw FeedException('Could not reach the feed: $error');
    }
  }
}

/// Parses the worker's payload. Kept separate from fetching so tests (and the
/// sample asset) can exercise it without a network.
FeedPayload parseFeed(String body) {
  final Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException catch (error) {
    throw FeedException('Feed is not valid JSON: ${error.message}');
  }
  if (decoded is! Map<String, dynamic>) {
    throw FeedException('Feed should be a JSON object with a "jobs" list.');
  }
  final rawJobs = decoded['jobs'];
  if (rawJobs is! List) {
    throw FeedException('Feed is missing its "jobs" list.');
  }
  final jobs = rawJobs
      .whereType<Map<String, dynamic>>()
      .map(Job.fromFeed)
      .where((job) => job.key.isNotEmpty && job.title.isNotEmpty)
      .toList(growable: false);
  return FeedPayload(
    jobs: jobs,
    generatedAt: DateTime.tryParse(decoded['generated_at']?.toString() ?? ''),
  );
}
