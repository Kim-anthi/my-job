import 'package:flutter/material.dart';

import '../../models/job.dart';

/// One row in the job list: enough to triage without opening the posting.
class JobCard extends StatelessWidget {
  const JobCard({
    super.key,
    required this.entry,
    required this.onTap,
    required this.onToggleSaved,
  });

  final JobEntry entry;
  final VoidCallback onTap;
  final VoidCallback onToggleSaved;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final job = entry.job;
    final subtitle = [
      job.company,
      if (job.location.isNotEmpty) job.location,
    ].where((part) => part.isNotEmpty).join(' · ');

    return Card(
      clipBehavior: Clip.antiAlias,
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _ScoreBadge(score: job.score),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          job.title,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (subtitle.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(
                            subtitle,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: entry.state.saved ? 'Remove bookmark' : 'Save',
                    onPressed: onToggleSaved,
                    icon: Icon(
                      entry.state.saved
                          ? Icons.bookmark
                          : Icons.bookmark_border,
                      color: entry.state.saved
                          ? theme.colorScheme.primary
                          : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _MetaChip(
                      icon: Icons.schedule,
                      label: formatAge(job.postedAt),
                    ),
                    _MetaChip(icon: Icons.travel_explore, label: job.source),
                    if (job.salary.isNotEmpty)
                      _MetaChip(icon: Icons.payments, label: job.salary),
                    if (entry.state.applied)
                      const _MetaChip(
                        icon: Icons.task_alt,
                        label: 'applied',
                        emphasize: true,
                      ),
                    ...job.tags
                        .take(3)
                        .map((tag) => _MetaChip(label: tag, subtle: true)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ScoreBadge extends StatelessWidget {
  const _ScoreBadge({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // 4 = one title keyword, 8+ = several strong signals. See the worker's
    // filters.py for the scoring rules.
    final strong = score >= 8;
    return Container(
      width: 34,
      height: 34,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: strong ? scheme.primary : scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        '$score',
        style: TextStyle(
          fontWeight: FontWeight.w700,
          color: strong ? scheme.onPrimary : scheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({
    this.icon,
    required this.label,
    this.subtle = false,
    this.emphasize = false,
  });

  final IconData? icon;
  final String label;
  final bool subtle;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = emphasize
        ? theme.colorScheme.primary
        : theme.colorScheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        color: subtle
            ? theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6)
            : Colors.transparent,
        border: subtle
            ? null
            : Border.all(color: theme.dividerColor.withValues(alpha: 0.6)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13, color: color),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: theme.textTheme.labelSmall?.copyWith(
              color: color,
              fontWeight: emphasize ? FontWeight.w700 : null,
            ),
          ),
        ],
      ),
    );
  }
}
