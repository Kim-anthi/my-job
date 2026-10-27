import 'package:flutter/material.dart';

import '../data/job_repository.dart';

import 'job_detail_page.dart';
import 'settings_page.dart';
import 'widgets/job_card.dart';

class JobListPage extends StatefulWidget {
  const JobListPage({super.key, required this.repository});

  final JobRepository repository;

  @override
  State<JobListPage> createState() => _JobListPageState();
}

class _JobListPageState extends State<JobListPage> {
  final TextEditingController _search = TextEditingController();
  JobFilter _filter = JobFilter.inbox;
  JobSort _sort = JobSort.newest;
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final repository = widget.repository;
    return ListenableBuilder(
      listenable: repository,
      builder: (context, _) {
        final entries = repository.view(
          filter: _filter,
          sort: _sort,
          query: _query,
        );
        return Scaffold(
          appBar: AppBar(
            title: const Text('Job radar'),
            actions: [
              IconButton(
                tooltip: _sort == JobSort.newest
                    ? 'Sorting by newest'
                    : 'Sorting by best match',
                onPressed: () => setState(() {
                  _sort = _sort == JobSort.newest
                      ? JobSort.bestMatch
                      : JobSort.newest;
                }),
                icon: Icon(
                  _sort == JobSort.newest ? Icons.schedule : Icons.star,
                ),
              ),
              IconButton(
                tooltip: 'Feed settings',
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => SettingsPage(repository: repository),
                  ),
                ),
                icon: const Icon(Icons.settings),
              ),
            ],
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(104),
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: TextField(
                      controller: _search,
                      onChanged: (value) => setState(() => _query = value),
                      decoration: InputDecoration(
                        isDense: true,
                        hintText: 'Search title, company, tag…',
                        prefixIcon: const Icon(Icons.search, size: 20),
                        suffixIcon: _query.isEmpty
                            ? null
                            : IconButton(
                                icon: const Icon(Icons.clear, size: 18),
                                onPressed: () {
                                  _search.clear();
                                  setState(() => _query = '');
                                },
                              ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                    ),
                  ),
                  SizedBox(
                    height: 44,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      children: [
                        for (final filter in JobFilter.values)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: FilterChip(
                              label: Text(
                                '${_filterLabel(filter)} ${repository.count(filter)}',
                              ),
                              selected: _filter == filter,
                              onSelected: (_) =>
                                  setState(() => _filter = filter),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          floatingActionButton: FloatingActionButton(
            onPressed: repository.busy ? null : repository.refresh,
            tooltip: 'Refresh feed',
            child: repository.busy
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2.5),
                  )
                : const Icon(Icons.refresh),
          ),
          body: Column(
            children: [
              if (repository.error != null)
                _Banner(
                  icon: Icons.error_outline,
                  message: repository.error!,
                  onAction: repository.refresh,
                  actionLabel: 'Retry',
                  tone: _BannerTone.error,
                )
              else if (repository.usingSampleFeed)
                _Banner(
                  icon: Icons.science_outlined,
                  message:
                      'Showing the bundled sample feed. Point the app at your '
                      'worker to see live jobs.',
                  actionLabel: 'Set feed',
                  onAction: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => SettingsPage(repository: repository),
                    ),
                  ),
                  tone: _BannerTone.info,
                ),
              Expanded(
                child: entries.isEmpty
                    ? _EmptyState(
                        filter: _filter,
                        hasAnything: repository.entries.isNotEmpty,
                        searching: _query.isNotEmpty,
                        onRefresh: repository.refresh,
                      )
                    : RefreshIndicator(
                        onRefresh: repository.refresh,
                        child: ListView.builder(
                          padding: const EdgeInsets.only(top: 4, bottom: 88),
                          itemCount: entries.length,
                          itemBuilder: (context, index) {
                            final entry = entries[index];
                            return JobCard(
                              key: ValueKey(entry.key),
                              entry: entry,
                              onToggleSaved: () =>
                                  repository.toggleSaved(entry.key),
                              onTap: () => Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => JobDetailPage(
                                    jobKey: entry.key,
                                    repository: repository,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  static String _filterLabel(JobFilter filter) => switch (filter) {
    JobFilter.inbox => 'Inbox',
    JobFilter.saved => 'Saved',
    JobFilter.applied => 'Applied',
    JobFilter.hidden => 'Hidden',
  };
}

enum _BannerTone { info, error }

class _Banner extends StatelessWidget {
  const _Banner({
    required this.icon,
    required this.message,
    required this.tone,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String message;
  final _BannerTone tone;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final background = tone == _BannerTone.error
        ? scheme.errorContainer
        : scheme.secondaryContainer;
    final foreground = tone == _BannerTone.error
        ? scheme.onErrorContainer
        : scheme.onSecondaryContainer;
    return Container(
      width: double.infinity,
      color: background,
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      child: Row(
        children: [
          Icon(icon, size: 18, color: foreground),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: foreground),
            ),
          ),
          if (actionLabel != null)
            TextButton(
              onPressed: onAction,
              child: Text(
                actionLabel!,
                style: TextStyle(color: foreground),
              ),
            ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.filter,
    required this.hasAnything,
    required this.searching,
    required this.onRefresh,
  });

  final JobFilter filter;
  final bool hasAnything;
  final bool searching;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (String headline, String detail) = switch (filter) {
      _ when searching => ('No match', 'Nothing matches that search.'),
      JobFilter.inbox when !hasAnything => (
        'Nothing cached yet',
        'Pull to refresh, or set your feed URL in settings.',
      ),
      JobFilter.inbox => (
        'Inbox clear',
        'Every cached job is hidden or handled.',
      ),
      JobFilter.saved => (
        'No saved jobs',
        'Tap the bookmark on a job to keep it here.',
      ),
      JobFilter.applied => (
        'No applications yet',
        'Mark a job as applied to track it here.',
      ),
      JobFilter.hidden => ('Nothing hidden', 'Jobs you hide show up here.'),
    };

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.radar,
              size: 56,
              color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 16),
            Text(headline, style: theme.textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(
              detail,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (!hasAnything) ...[
              const SizedBox(height: 18),
              FilledButton.tonalIcon(
                onPressed: onRefresh,
                icon: const Icon(Icons.refresh),
                label: const Text('Load feed'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
