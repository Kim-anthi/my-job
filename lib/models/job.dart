/// Models mirroring the radar worker's `latest.json` feed, plus the local
/// state the worker cannot know about (what *you* did with each job).
library;

import 'dart:convert';

/// A posting as published by the worker. Immutable: the feed owns this data.
class Job {
  const Job({
    required this.key,
    required this.source,
    required this.title,
    required this.company,
    required this.url,
    this.location = '',
    this.salary = '',
    this.summary = '',
    this.status = 'new',
    this.tags = const [],
    this.reasons = const [],
    this.score = 0,
    this.postedAt,
    this.firstSeen,
  });

  final String key;
  final String source;
  final String title;
  final String company;
  final String url;
  final String location;
  final String salary;
  final String summary;

  /// `notified` or `new`, as set by the worker.
  final String status;
  final List<String> tags;

  /// Why the filter engine kept this job, e.g. `title:flutter`.
  final List<String> reasons;
  final int score;
  final DateTime? postedAt;
  final DateTime? firstSeen;

  /// Parsed from the worker's JSON. Tolerant by design: a feed written by a
  /// newer worker must not crash an older build of the app.
  factory Job.fromFeed(Map<String, dynamic> json) {
    return Job(
      key: _string(json['key']),
      source: _string(json['source']),
      title: _string(json['title']),
      company: _string(json['company']),
      url: _string(json['url']),
      location: _string(json['location']),
      salary: _string(json['salary']),
      summary: _string(json['summary']),
      status: _string(json['status'], fallback: 'new'),
      tags: _stringList(json['tags']),
      reasons: _stringList(json['reasons']),
      score: _int(json['score']),
      postedAt: _date(json['posted_at']),
      firstSeen: _date(json['first_seen']),
    );
  }

  factory Job.fromRow(Map<String, Object?> row) {
    return Job(
      key: _string(row['key']),
      source: _string(row['source']),
      title: _string(row['title']),
      company: _string(row['company']),
      url: _string(row['url']),
      location: _string(row['location']),
      salary: _string(row['salary']),
      summary: _string(row['summary']),
      status: _string(row['status'], fallback: 'new'),
      tags: _stringList(_decode(row['tags'])),
      reasons: _stringList(_decode(row['reasons'])),
      score: _int(row['score']),
      postedAt: _date(row['posted_at']),
      firstSeen: _date(row['first_seen']),
    );
  }

  Map<String, Object?> toRow() => {
    'key': key,
    'source': source,
    'title': title,
    'company': company,
    'url': url,
    'location': location,
    'salary': salary,
    'summary': summary,
    'status': status,
    'tags': jsonEncode(tags),
    'reasons': jsonEncode(reasons),
    'score': score,
    'posted_at': postedAt?.toIso8601String(),
    'first_seen': firstSeen?.toIso8601String(),
  };

  /// Whole days since the posting went up, or null when the board gave no date.
  int? get ageInDays {
    final posted = postedAt;
    if (posted == null) return null;
    return DateTime.now().toUtc().difference(posted.toUtc()).inDays;
  }

  static String _string(Object? value, {String fallback = ''}) {
    if (value == null) return fallback;
    final text = value.toString().trim();
    return text.isEmpty ? fallback : text;
  }

  static int _int(Object? value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static DateTime? _date(Object? value) {
    if (value == null) return null;
    return DateTime.tryParse(value.toString());
  }

  static List<String> _stringList(Object? value) {
    if (value is List) {
      return value
          .map((item) => item?.toString().trim() ?? '')
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const [];
  }

  static Object? _decode(Object? value) {
    if (value is! String || value.isEmpty) return null;
    try {
      return jsonDecode(value);
    } on FormatException {
      return null;
    }
  }
}

/// What you did with a job. Lives in its own table so refreshing the feed can
/// never overwrite it.
class JobState {
  const JobState({
    this.saved = false,
    this.applied = false,
    this.hidden = false,
    this.note = '',
    this.updatedAt,
  });

  final bool saved;
  final bool applied;
  final bool hidden;
  final String note;
  final DateTime? updatedAt;

  static const JobState none = JobState();

  bool get isEmpty => !saved && !applied && !hidden && note.isEmpty;

  factory JobState.fromRow(Map<String, Object?> row) => JobState(
    saved: (row['saved'] as int? ?? 0) == 1,
    applied: (row['applied'] as int? ?? 0) == 1,
    hidden: (row['hidden'] as int? ?? 0) == 1,
    note: (row['note'] as String?) ?? '',
    updatedAt: DateTime.tryParse(row['updated_at']?.toString() ?? ''),
  );

  Map<String, Object?> toRow(String key) => {
    'key': key,
    'saved': saved ? 1 : 0,
    'applied': applied ? 1 : 0,
    'hidden': hidden ? 1 : 0,
    'note': note,
    'updated_at': (updatedAt ?? DateTime.now()).toIso8601String(),
  };

  JobState copyWith({bool? saved, bool? applied, bool? hidden, String? note}) =>
      JobState(
        saved: saved ?? this.saved,
        applied: applied ?? this.applied,
        hidden: hidden ?? this.hidden,
        note: note ?? this.note,
        updatedAt: DateTime.now(),
      );
}

/// A job paired with your state for it: what the list and detail pages render.
class JobEntry {
  const JobEntry({required this.job, this.state = JobState.none});

  final Job job;
  final JobState state;

  String get key => job.key;
}

/// `2026-10-26T14:08:25Z` -> `today`, `3d`, `2w`. Avoids an intl dependency.
String formatAge(DateTime? moment) {
  if (moment == null) return 'undated';
  final days = DateTime.now().toUtc().difference(moment.toUtc()).inDays;
  if (days <= 0) return 'today';
  if (days == 1) return 'yesterday';
  if (days < 14) return '${days}d ago';
  if (days < 60) return '${(days / 7).floor()}w ago';
  return '${(days / 30).floor()}mo ago';
}
