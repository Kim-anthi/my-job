/// Single source of truth for the UI: owns the cached jobs, your state, and
/// the refresh lifecycle.
library;

import 'package:flutter/foundation.dart';

import '../models/job.dart';
import 'app_database.dart';
import 'feed_client.dart';

const String kFeedSourceSetting = 'feed_source';
const String kLastRefreshSetting = 'last_refresh';

enum JobFilter { inbox, saved, applied, hidden }

enum JobSort { newest, bestMatch }

class JobRepository extends ChangeNotifier {
  JobRepository({required AppDatabase database, FeedClient? feedClient})
    : _database = database,
      _feedClient = feedClient ?? HttpFeedClient();

  final AppDatabase _database;
  final FeedClient _feedClient;

  List<JobEntry> _entries = const [];
  String _feedSource = kSampleFeedSource;
  DateTime? _lastRefresh;
  bool _busy = false;
  String? _error;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Every notification goes through here. Each mutation awaits a database
  /// write first, so the listener set can be torn down (page popped, app
  /// closing) before the write lands - and notifying then throws.
  void _notify() {
    if (!_disposed) notifyListeners();
  }

  List<JobEntry> get entries => _entries;
  String get feedSource => _feedSource;
  DateTime? get lastRefresh => _lastRefresh;
  bool get busy => _busy;
  String? get error => _error;
  bool get usingSampleFeed => _feedSource == kSampleFeedSource;

  /// Reads the cache and settings. Fast: no network.
  Future<void> load() async {
    _feedSource = await _database.setting(kFeedSourceSetting) ?? kSampleFeedSource;
    _lastRefresh = DateTime.tryParse(
      await _database.setting(kLastRefreshSetting) ?? '',
    );
    _entries = await _database.entries();
    _notify();
  }

  /// Pulls the feed and merges it into the cache. Your state is untouched.
  Future<void> refresh() async {
    if (_busy) return;
    _busy = true;
    _error = null;
    _notify();
    try {
      final payload = await _feedClient.fetch(_feedSource);
      await _database.upsertJobs(payload.jobs);
      _lastRefresh = payload.generatedAt ?? DateTime.now();
      await _database.setSetting(
        kLastRefreshSetting,
        _lastRefresh!.toIso8601String(),
      );
      _entries = await _database.entries();
    } on FeedException catch (error) {
      _error = error.message;
    } catch (error) {
      _error = 'Refresh failed: $error';
    } finally {
      _busy = false;
      _notify();
    }
  }

  Future<void> setFeedSource(String source) async {
    final trimmed = source.trim();
    if (trimmed.isEmpty || trimmed == _feedSource) return;
    _feedSource = trimmed;
    await _database.setSetting(kFeedSourceSetting, trimmed);
    _notify();
    await refresh();
  }

  Future<void> toggleSaved(String key) =>
      _mutate(key, (state) => state.copyWith(saved: !state.saved));

  /// Marking a job applied also saves it: it is part of your pipeline now.
  Future<void> toggleApplied(String key) => _mutate(key, (state) {
    final applied = !state.applied;
    return state.copyWith(applied: applied, saved: applied || state.saved);
  });

  Future<void> toggleHidden(String key) =>
      _mutate(key, (state) => state.copyWith(hidden: !state.hidden));

  Future<void> setNote(String key, String note) =>
      _mutate(key, (state) => state.copyWith(note: note.trim()));

  Future<void> _mutate(String key, JobState Function(JobState) change) async {
    final index = _entries.indexWhere((entry) => entry.key == key);
    if (index < 0) return;
    final updated = change(_entries[index].state);
    await _database.saveState(key, updated);
    // Swap in a new list so ListenableBuilder sees a change.
    final next = List<JobEntry>.of(_entries);
    next[index] = JobEntry(job: _entries[index].job, state: updated);
    _entries = next;
    _notify();
  }

  /// The visible list for a tab, after search and sorting.
  List<JobEntry> view({
    required JobFilter filter,
    JobSort sort = JobSort.newest,
    String query = '',
  }) {
    final needle = query.trim().toLowerCase();
    final result = _entries.where((entry) {
      switch (filter) {
        case JobFilter.inbox:
          if (entry.state.hidden) return false;
        case JobFilter.saved:
          if (!entry.state.saved) return false;
        case JobFilter.applied:
          if (!entry.state.applied) return false;
        case JobFilter.hidden:
          if (!entry.state.hidden) return false;
      }
      if (needle.isEmpty) return true;
      final job = entry.job;
      return job.title.toLowerCase().contains(needle) ||
          job.company.toLowerCase().contains(needle) ||
          job.location.toLowerCase().contains(needle) ||
          job.tags.any((tag) => tag.toLowerCase().contains(needle));
    }).toList();

    result.sort((a, b) {
      if (sort == JobSort.bestMatch) {
        final byScore = b.job.score.compareTo(a.job.score);
        if (byScore != 0) return byScore;
      }
      final left = a.job.firstSeen ?? a.job.postedAt;
      final right = b.job.firstSeen ?? b.job.postedAt;
      if (left == null && right == null) return 0;
      if (left == null) return 1;
      if (right == null) return -1;
      return right.compareTo(left);
    });
    return result;
  }

  int count(JobFilter filter) => view(filter: filter).length;
}
