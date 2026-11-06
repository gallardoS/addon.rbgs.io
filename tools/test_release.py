"""Exercise the actual ZIP and upload wire format without network or publishing."""
import json
import tempfile
import unittest
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import package_forever
import prepare_release
import publish_curseforge as cf


class ReleaseTests(unittest.TestCase):
    def env(self, attempt='1'):
        return {'GITHUB_RUN_NUMBER': '73', 'GITHUB_RUN_ATTEMPT': attempt, 'GITHUB_SHA': 'a' * 40}

    def test_ci_zip_stamps_both_versions_excludes_debugger_and_leaves_source_unchanged(self):
        source = package_forever.ROOT / 'rbgs.io'
        before = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            release = prepare_release.prepare(self.env(), directory)
            archive = Path(directory) / release['archive']
            with ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertTrue(all(p.startswith('rbgs.io/') for p in z.namelist()))
                self.assertFalse(any('Compatibility' in p or '_TBC' in p for p in z.namelist()))
                toc = z.read('rbgs.io/rbgs.io.toc').decode()
                version = next(s.split(': ', 1)[1] for s in toc.splitlines() if s.startswith('## Version:'))
                self.assertTrue(version.endswith('-alpha.73.1'))
                self.assertIn(f'addonVersion="{version}"', z.read('rbgs.io/ForeverAdapter.lua').decode())
                self.assertIn('rbgs.io/LICENSE', z.namelist())
                self.assertEqual(release['projectId'], 1783290)
                self.assertIn('a' * 40, release['metadata']['changelog'])
            retry = prepare_release.prepare(self.env('2'), directory)
            self.assertNotEqual(release['archive'], retry['archive'])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_ci_identity_is_rejected(self):
        for key, value in [('GITHUB_RUN_NUMBER', '0'), ('GITHUB_RUN_ATTEMPT', '../bad'), ('GITHUB_SHA', 'not-a-sha')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                env = self.env(); env[key] = value
                with self.assertRaises(ValueError):
                    prepare_release.prepare(env, directory)

    def test_game_version_requires_exact_forever_match(self):
        rows = [{'id': 100, 'name': '1.60.1', 'gameVersionTypeID': 88568},
                {'id': 200, 'name': '1.60.1', 'gameVersionTypeID': 73246}]
        self.assertEqual(cf.resolve_version(rows, '1.60.1', 88568), 100)
        for versions in [[], rows[1:], rows + [rows[0]], {'errorMessage': 'fixture'}, [None]]:
            with self.assertRaises(ValueError):
                cf.resolve_version(versions, '1.60.1', 88568)

    def test_upload_contains_exact_zip_alpha_metadata_and_version_id(self):
        with tempfile.TemporaryDirectory() as directory:
            release = prepare_release.prepare(self.env(), directory)
            versions = [{'id': 100, 'name': '1.60.1', 'gameVersionTypeID': 88568}]
            with patch.object(cf, 'request_json', side_effect=[versions, {'id': 123}]) as api:
                self.assertEqual(cf.publish(directory, 'fixture-token'), 123)
            self.assertEqual(api.call_count, 2)
            args = api.call_args_list[1].args
            self.assertEqual(args[0], '/projects/1783290/upload-file')
            message = BytesParser().parsebytes(('Content-Type: ' + args[3] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + args[2])
            metadata_part, file_part = message.get_payload()
            metadata = json.loads(metadata_part.get_payload(decode=True))
            self.assertEqual(metadata['gameVersions'], [100])
            self.assertEqual(metadata['releaseType'], 'alpha')
            self.assertEqual(file_part.get_filename(), release['archive'])
            self.assertEqual(file_part.get_payload(decode=True), (Path(directory) / release['archive']).read_bytes())
            self.assertEqual(json.loads((Path(directory) / 'curseforge-result.json').read_text())['id'], 123)

    def test_missing_token_and_uncertain_upload_never_retry(self):
        with patch.object(cf, 'request_json') as api:
            with self.assertRaisesRegex(ValueError, 'CF_API_KEY'):
                cf.publish('not-needed', '')
            api.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            prepare_release.prepare(self.env(), directory)
            versions = [{'id': 100, 'name': '1.60.1', 'gameVersionTypeID': 88568}]
            with patch.object(cf, 'request_json', side_effect=[versions, RuntimeError('lost reply')]) as api:
                with self.assertRaises(RuntimeError):
                    cf.publish(directory, 'fixture-token')
                self.assertEqual(api.call_count, 2)


if __name__ == '__main__':
    unittest.main()
