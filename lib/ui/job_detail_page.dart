import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/job_repository.dart';
import '../models/job.dart';

class JobDetailPage extends StatelessWidget {
  const JobDetailPage({
    super.key,
    required this.jobKey,
    required this.repository,
  });

  final String jobKey;
  final JobRepository repository;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: repository,
      builder: (context, _) {
        final entry = repository.entries
            .where((candidate) => candidate.key == jobKey)
            .firstOrNull;
        if (entry == null) {
          return const Scaffold(
            body: Center(child: Text('This job is no longer cached.')),
          );
        }
        final job = entry.job;
        final theme = Theme.of(context);

        return Scaffold(
          appBar: AppBar(
            title: Text(job.company.isEmpty ? 'Job' : job.company),
            actions: [
              IconButton(
                tooltip: entry.state.hidden ? 'Unhide' : 'Hide',
                onPressed: () => repository.toggleHidden(jobKey),
                icon: Icon(
                  entry.state.hidden
                      ? Icons.visibility_off
                      : Icons.visibility_outlined,
                ),
              ),
              IconButton(
                tooltip: entry.state.saved ? 'Remove bookmark' : 'Save',
                onPressed: () => repository.toggleSaved(jobKey),
                icon: Icon(
                  entry.state.saved ? Icons.bookmark : Icons.bookmark_border,
                ),
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(18, 10, 18, 96),
            children: [
              Text(job.title, style: theme.textTheme.headlineSmall),
              const SizedBox(height: 10),
              _Facts(job: job),
              if (job.tags.isNotEmpty) ...[
                const SizedBox(height: 14),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final tag in job.tags)
                      Chip(
                        label: Text(tag),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize:
                            MaterialTapTargetSize.shrinkWrap,
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 18),
              if (job.summary.isNotEmpty) ...[
                Text('Summary', style: theme.textTheme.titleSmall),
                const SizedBox(height: 6),
                Text(job.summary, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 6),
                Text(
                  'Trimmed by the worker — open the posting for the full text.',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 18),
              ],
              if (job.reasons.isNotEmpty) ...[
                Text('Why it matched', style: theme.textTheme.titleSmall),
                const SizedBox(height: 6),
                Text(
                  job.reasons.join(' · '),
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 18),
              ],
              Card(
                margin: EdgeInsets.zero,
                child: ListTile(
                  leading: const Icon(Icons.edit_note),
                  title: Text(
                    entry.state.note.isEmpty ? 'Add a note' : entry.state.note,
                  ),
                  subtitle: entry.state.note.isEmpty
                      ? const Text('Recruiter name, follow-up date, salary ask…')
                      : null,
                  onTap: () => _editNote(context, entry),
                ),
              ),
            ],
          ),
          bottomNavigationBar: SafeArea(
            minimum: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Row(
              children: [
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: () => repository.toggleApplied(jobKey),
                    icon: Icon(
                      entry.state.applied
                          ? Icons.task_alt
                          : Icons.radio_button_unchecked,
                    ),
                    label: Text(entry.state.applied ? 'Applied' : 'Mark applied'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: job.url.isEmpty
                        ? null
                        : () => _openPosting(context, job.url),
                    icon: const Icon(Icons.open_in_new),
                    label: const Text('Open'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _openPosting(BuildContext context, String url) async {
    final messenger = ScaffoldMessenger.of(context);
    final uri = Uri.tryParse(url);
    if (uri == null) {
      messenger.showSnackBar(const SnackBar(content: Text('Invalid link.')));
      return;
    }
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened) {
      messenger.showSnackBar(
        SnackBar(content: Text('Could not open $url')),
      );
    }
  }

  Future<void> _editNote(BuildContext context, JobEntry entry) async {
    final controller = TextEditingController(text: entry.state.note);
    final note = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Note'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 4,
          decoration: const InputDecoration(hintText: 'Anything worth keeping'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (note != null) {
      await repository.setNote(entry.key, note);
    }
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.job});

  final Job job;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final facts = <(IconData, String)>[
      if (job.company.isNotEmpty) (Icons.business, job.company),
      if (job.location.isNotEmpty) (Icons.place_outlined, job.location),
      if (job.salary.isNotEmpty) (Icons.payments_outlined, job.salary),
      (Icons.schedule, 'Posted ${formatAge(job.postedAt)}'),
      (Icons.travel_explore, job.source),
      (Icons.star_outline, 'Match score ${job.score}'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final (icon, label) in facts)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(
              children: [
                Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(label, style: theme.textTheme.bodyMedium),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
