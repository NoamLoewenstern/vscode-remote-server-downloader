from pathlib import Path
from utils import coro

import aiohttp
from vscode import PLATFORMS, Platform, download_vscode_server, get_vscode_tags
import typer
app = typer.Typer()


SCRIPT_DIR = Path(__file__).parent.resolve()
VALID_PLATFORM_ARG = list(PLATFORMS.keys()) + ['all']

@coro
async def vscode_version_cb(ctx: typer.Context, value: str):
    if ctx.resilient_parsing:
        return
    async with aiohttp.ClientSession() as session:
        vscode_tags = await get_vscode_tags(session)
        if value not in vscode_tags.keys():
            raise typer.BadParameter(f'Invalid Version: {value}. Valid Versions: {list(vscode_tags.keys())}')
        return value




@app.command('list_versions')
@coro
async def list_versions():
    async with aiohttp.ClientSession() as session:
        vscode_tags = await get_vscode_tags(session)
        typer.echo(list(vscode_tags.keys()))


def complete_platform(platform: str):
    completion = []
    for name in VALID_PLATFORM_ARG:
        if name.startswith(platform):
            completion.append(name)
    return completion



@app.command('download_version')
@coro
async def download(version: str = typer.Argument(..., callback=vscode_version_cb),
                   platform: Platform = Platform.all,
                   directory: Path = typer.Option('out'),
                   ):
    async with aiohttp.ClientSession() as session:
        await download_vscode_server(session=session, version=version, platform=platform, directory=directory)


@app.command('download_last_versions')
@coro
async def download_latest(platform: str = Platform.all,
                          directory: Path = typer.Option('out'),
                          last: int = 1):
    async with aiohttp.ClientSession() as session:
        vscode_tags = await get_vscode_tags(session)
        versions = sorted(list(vscode_tags.keys()), reverse=True)[:last]
        for version in versions:
            await download_vscode_server(session=session, version=version, platform=platform, directory=directory)



if __name__ == '__main__':
    app()

