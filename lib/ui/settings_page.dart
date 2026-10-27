import 'package:flutter/material.dart';

import '../data/feed_client.dart';
import '../data/job_repository.dart';
import '../models/job.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.repository});

  final JobRepository repository;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _source = TextEditingController(
    text: widget.repository.feedSource,
  );

  @override
  void dispose() {
    _source.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final repository = widget.repository;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Feed')),
      body: ListenableBuilder(
        listenable: repository,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 32),
          children: [
            Text('Feed source', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            TextField(
              controller: _source,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: InputDecoration(
                border: const OutlineInputBorder(),
                hintText: 'https://raw.githubusercontent.com/…/latest.json',
                helperMaxLines: 3,
                helperText:
                    'The URL of the worker\'s data/latest.json, or '
                    '"$kSampleFeedSource" for the bundled example.',
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                FilledButton.icon(
                  onPressed: repository.busy
                      ? null
                      : () async {
                          await repository.setFeedSource(_source.text);
                          if (context.mounted &&
                              repository.error == null &&
                              Navigator.of(context).canPop()) {
                            Navigator.of(context).pop();
                          }
                        },
                  icon: const Icon(Icons.save),
                  label: const Text('Save and refresh'),
                ),
                const SizedBox(width: 10),
                TextButton(
                  onPressed: repository.busy
                      ? null
                      : () {
                          _source.text = kSampleFeedSource;
                          repository.setFeedSource(kSampleFeedSource);
                        },
                  child: const Text('Use sample'),
                ),
              ],
            ),
            if (repository.error != null) ...[
              const SizedBox(height: 12),
              Text(
                repository.error!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
            const Divider(height: 36),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.inventory_2_outlined),
              title: const Text('Cached jobs'),
              subtitle: Text('${repository.entries.length} stored locally'),
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.update),
              title: const Text('Last refresh'),
              subtitle: Text(
                repository.lastRefresh == null
                    ? 'Never'
                    : '${formatAge(repository.lastRefresh)} '
                          '(${repository.lastRefresh!.toLocal()})',
              ),
            ),
            const Divider(height: 36),
            Text('Where the feed comes from', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Text(
              'The radar worker in radar/ writes data/latest.json on every run '
              'and the GitHub Actions workflow commits it. Use that file\'s raw '
              'URL here.\n\n'
              'To preview a feed you just generated locally, serve it:\n'
              '    cd radar/data && python -m http.server 8000\n'
              'then use http://localhost:8000/latest.json\n\n'
              'Private repositories do not serve raw files without a token, so '
              'either keep the repo public or publish the feed elsewhere.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
