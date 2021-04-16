from enum import Enum
import json
from pathlib import Path
import subprocess
from typing import NewType
from utils import StrPath, download_file
import aiohttp
import asyncio
from pydantic import BaseModel
import os
import sys
TAGS_URL = 'https://api.github.com/repos/microsoft/vscode/git/refs/tags'
TAG_INFO_URL = 'https://api.github.com/repos/microsoft/vscode/git/tags/{tag_hash}'
RELEASES_URL = 'https://api.github.com/repos/microsoft/vscode/releases'
# COMMITS_URL = 'https://api.github.com/repos/microsoft/vscode/commits?sha={tag_hash}'
VSCODE_SERVER_DOWNLOAD_URL = 'https://update.code.visualstudio.com/commit:{commit}/{platform}/stable'


class Platform(str, Enum):
    windows = 'windows'
    linux = 'linux'
    alpine = 'alpine'
    all = 'all'

PLATFORMS = {
    'windows': 'server-win32-x64',
    'linux': 'server-linux-x64',
    'alpine': 'server-linux-alpine',
}
COLON_UNICODE = '\uf03a'


def get_vscode_exe_path():
    if sys.platform.startswith('win'):
        out = subprocess.check_output('where code'.split(' '))
        binaries = out.strip().decode().split('\r\n')
        vscode_exe = [path for path in binaries if path.endswith('.cmd')][0]
    elif sys.platform.startswith('linux'):
        out = subprocess.check_output('which code'.split(' '))
        vscode_exe = out.strip().decode().split('\r\n')[0]
    else:
        raise Exception(f'Unknown sys.platform: {sys.platform}')
    if not os.path.isfile(vscode_exe):
        raise Exception(f'No VScode-binary exe file: {vscode_exe}')
    return vscode_exe


def get_vscode_stats() -> dict:
    code_path = get_vscode_exe_path()
    code_stats = subprocess.check_output([code_path, '-v'])
    version, commit_hex, platform, *_ = code_stats.decode().split('\n')
    return dict(version=version, commit_hex=commit_hex, platform=platform)


class TagRefTagObject(BaseModel):
    sha: str
    type: str
    url: str


class VSCodeTagRef(BaseModel):
    ref: str
    node_id: str
    url: str
    object: TagRefTagObject

    @property
    def version(self) -> str:
        return Path(self.ref).name


class ListVSCodeTagRefTag(BaseModel):
    __root__: list[VSCodeTagRef]


VSCodeTags = NewType('VSCodeTags', dict[str, VSCodeTagRef])

global cache_tags
global cache_releases_versions
cache_releases_versions: list[str] = None
cache_tags: VSCodeTags = None


async def get_official_releases_versions(session: aiohttp.ClientSession) -> list[str]:
    global cache_releases_versions
    if cache_releases_versions:
        return cache_releases_versions
    async with session.get(RELEASES_URL) as resp:
        content = await resp.text()
        cache_releases_versions = [r['tag_name'] for r in json.loads(content)]
        return cache_releases_versions


async def get_commit_hash_from_tag_hash(session: aiohttp.ClientSession, tag_hash: str) -> str:
    async with session.get(TAG_INFO_URL.format(tag_hash=tag_hash)) as resp:
        content = await resp.text()
        data: dict = json.loads(content)
        if data.get('object', {}).get('type') != 'commit':
            raise ValueError(
                'resp from GithubAPI did not return intended data -> getting commit-hash from tag-hash.')
        return data['object']['sha']


async def get_vscode_tags(session: aiohttp.ClientSession) -> VSCodeTags:
    global cache_tags
    if cache_tags:
        return cache_tags
    async with session.get(TAGS_URL) as resp:
        content = await resp.text()
        vscode_tags = ListVSCodeTagRefTag.parse_raw(content).__root__
        official_releases_versions = await get_official_releases_versions(session)
        vscode_tags_by_version: VSCodeTags = {tag.version: tag for tag in vscode_tags
                                              if tag.version in official_releases_versions}
        latest_vscode_tag = max(vscode_tags_by_version.keys())
        vscode_tags_by_version['latest'] = vscode_tags_by_version[latest_vscode_tag]
        cache_tags = vscode_tags_by_version
        return vscode_tags_by_version


async def download_vscode_server(*,
                                 session: aiohttp.ClientSession,
                                 version: str,
                                 platform: Platform,
                                 directory: StrPath):
    vscode_tags = await get_vscode_tags(session)
    if vscode_tags[version].object.type == 'commit':
        commit_hash = vscode_tags[version].object.sha
    elif vscode_tags[version].object.type == 'tag':
        commit_hash = await get_commit_hash_from_tag_hash(session, tag_hash=vscode_tags[version].object.sha)
    else:
        raise ValueError(f'Unexpected version {version} object.type value {vscode_tags[version].object}.')
    if version == 'latest':
        version = vscode_tags[version].version
    directory = Path(directory) / version / f'commit{COLON_UNICODE}{commit_hash}'
    directory.mkdir(exist_ok=True, parents=True)
    platforms = list(PLATFORMS.values()) if platform == 'all' else [PLATFORMS[platform]]
    download_tasks = []
    for os_platform in platforms:
        dst_file = directory / os_platform / 'stable'
        if dst_file.exists():
            continue
        dst_file.parent.mkdir()
        url = VSCODE_SERVER_DOWNLOAD_URL.format(commit=commit_hash, platform=os_platform)
        task = asyncio.create_task(download_file(session, url, dst_file))
        download_tasks.append(task)
    await asyncio.gather(*download_tasks)
