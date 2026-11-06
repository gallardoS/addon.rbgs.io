"""Upload a prepared Forever Alpha through CurseForge's author Upload API."""
import argparse
import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = 'https://wow.curseforge.com/api'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(path, token, data=None, content_type=None):
    headers = {'X-Api-Token': token, 'Accept': 'application/json', 'User-Agent': 'rbgs.io-release'}
    if content_type:
        headers['Content-Type'] = content_type
    request = Request(BASE_URL + path, data=data, headers=headers)
    try:
        with build_opener(NoRedirect).open(request, timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        # Never dump request headers or arbitrary server bodies into CI logs.
        raise RuntimeError(f'CurseForge HTTP {error.code}: check the token, project permissions and game version') from None
    except URLError:
        raise RuntimeError('Cannot reach CurseForge; inspect project files before rerunning an uncertain upload') from None


def resolve_version(versions, name, type_id):
    if not isinstance(versions, list) or any(not isinstance(v, dict) for v in versions):
        raise ValueError('CurseForge returned an invalid game-version list')
    matches = [v['id'] for v in versions if v.get('name') == name and v.get('gameVersionTypeID') == type_id]
    if len(matches) != 1 or type(matches[0]) is not int or matches[0] <= 0:
        raise ValueError('CurseForge must return exactly one matching Forever game version')
    return matches[0]


def multipart(metadata, filename, contents, boundary):
    if Path(filename).name != filename or any(c in filename for c in '\r\n"'):
        raise ValueError('Invalid archive filename')
    prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'.encode()
    prefix += json.dumps(metadata).encode('utf-8')
    prefix += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/zip\r\n\r\n'.encode()
    return prefix + contents + f'\r\n--{boundary}--\r\n'.encode()


def publish(release_dir, token):
    if not token:
        raise ValueError('Add the repository Actions secret CF_API_KEY before publishing')
    release_dir = Path(release_dir)
    release = json.loads((release_dir / 'release.json').read_text(encoding='utf-8'))
    name = release['archive']
    if Path(name).name != name or not name.endswith('-forever.zip'):
        raise ValueError('Invalid Forever archive name')
    if release['gameVersionTypeId'] != 88568 or release['metadata']['releaseType'] != 'alpha':
        raise ValueError('Only Forever Alpha publication is enabled')
    project_id = release['projectId']
    if type(project_id) is not int or project_id <= 0:
        raise ValueError('Invalid CurseForge project ID')
    versions = request_json('/game/wow/versions', token)
    metadata = dict(release['metadata'])
    metadata['gameVersions'] = [resolve_version(versions, release['gameVersion'], release['gameVersionTypeId'])]
    boundary = 'rbgs-' + uuid.uuid4().hex
    body = multipart(metadata, name, (release_dir / name).read_bytes(), boundary)
    # No automatic POST retry: a lost reply may already have created a file.
    result = request_json(f'/projects/{project_id}/upload-file', token, body, f'multipart/form-data; boundary={boundary}')
    if not isinstance(result, dict) or type(result.get('id')) is not int or result['id'] <= 0:
        raise RuntimeError('Upload reply has no file ID; check CurseForge before retrying')
    (release_dir / 'curseforge-result.json').write_text(json.dumps(result) + '\n', encoding='utf-8')
    print(f'CurseForge accepted file {result["id"]}; approval/public availability is managed by CurseForge')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f'\nCurseForge accepted file **{result["id"]}** for project {project_id}.\n')
    return result['id']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        publish(args.release_dir, os.environ.get('CF_API_KEY', ''))
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
