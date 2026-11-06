"""Create a uniquely versioned Forever CI package and CurseForge metadata."""
import json
import os
import re
from pathlib import Path

from package_forever import ROOT, package


def prepare(env=os.environ, output=None):
    toc = (ROOT / 'rbgs.io/rbgs.io.toc').read_text(encoding='utf-8')
    base = re.search(r'^## Version: (\d+\.\d+\.\d+)(?:-\S+)?$', toc, re.MULTILINE)
    project = re.search(r'^## X-Curse-Project-ID: (\d+)$', toc, re.MULTILINE)
    if not base or not project:
        raise ValueError('Missing product version or CurseForge project ID in TOC')
    run, attempt = env.get('GITHUB_RUN_NUMBER', ''), env.get('GITHUB_RUN_ATTEMPT', '')
    if not re.fullmatch(r'[1-9]\d*', run) or not re.fullmatch(r'[1-9]\d*', attempt):
        raise ValueError('Positive GITHUB_RUN_NUMBER and GITHUB_RUN_ATTEMPT are required')
    version = f'{base[1]}-alpha.{run}.{attempt}'
    output = Path(output) if output else ROOT / 'releases'
    archive = package(version, output / f'rbgs.io-{version}-forever.zip')
    sha = env.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('A full GITHUB_SHA is required for release provenance')
    # Use the native game's version declared in the adapter's release target,
    # never Classic/TBC just because this project already has TBC files.
    game_version = '1.60.1'
    changelog = f'# rbgs.io {version} — Forever\n\nSource commit: `{sha}`\n\n'
    changelog += (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    (output / 'changelog.md').write_text(changelog, encoding='utf-8')
    release = {
        'projectId': int(project[1]), 'archive': archive.name,
        'gameVersion': game_version, 'gameVersionTypeId': 88568,
        'metadata': {'displayName': f'rbgs.io {version} — Forever',
                     'releaseType': 'alpha', 'changelogType': 'markdown',
                     'changelog': changelog},
    }
    (output / 'release.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    summary = env.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f'Built **{version}** for Forever {game_version}.\n\nZIP: `{archive.name}`\n')
    return release


if __name__ == '__main__':
    print(prepare()['archive'])
