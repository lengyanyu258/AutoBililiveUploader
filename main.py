import asyncio
import os
import shutil
import sys
import threading
import time
import tomllib
from multiprocessing import Process, Value
from pathlib import Path
from typing import Dict, Tuple

import click
from flask import Flask, jsonify
from flask.cli import FlaskGroup

from app import create_app
from app.config import authors
from app.core import main

app = create_app()


@click.group(epilog="使用 -h, --help 查看命令具体用法")
@click.help_option("-h", "--help")
@click.version_option(
    app.version,
    "-v",
    "--version",
    package_name=app.title,
    message="%(package)s, version %(version)s\n{license}, licensed by {author} 2023年6月7日".format(
        license=app.config["LICENSE"]["name"], author=authors[0]
    ),
)
def cli():
    """自动压制並上传哔哩哔哩录播文件至网盘。

    Support：录播姬、blrec
    """
    pass


def validate_dirs(ctx: click.Context, param: click.Parameter, value: Tuple[str]):
    dirs_path = tuple(
        Path(v.encode().translate(None, delete='*?"<>|'.encode()).decode())
        for v in value
    )
    for dir_path in dirs_path:
        if not dir_path.exists():
            raise click.BadParameter(f"目录 {dir_path.as_posix()!r} 不存在。", ctx, param)
    return dirs_path


@cli.command(epilog="更多配置请查看 instance/config.toml 文件。", no_args_is_help=True)
@click.help_option("-h", "--help")
@click.argument(
    "dirs_path",
    type=click.Path(exists=False, file_okay=False, writable=True, path_type=str),
    callback=validate_dirs,
    nargs=-1,
    metavar="目录1 [目录2, ...]",
)
@click.option("-a", "--all", is_flag=True, help="Generate all.")
@click.option("-u", "--upload", is_flag=True, help="Upload generated files.")
@click.option(
    " /-nl", "--limited/--no-limited", default=True, help="Do not limit video rate."
)
@click.option(
    " /-np",
    "--preparation/--no-preparation",
    default=True,
    help="Do not generate preparation.",
)
@click.option("-ev", "--early_video", is_flag=True, help="Generate early video.")
@click.option("-dv", "--danmaku_video", is_flag=True, help="Generate danmaku video.")
def gen(dirs_path: Tuple[Path], **flags: bool):
    """压制並上传哔哩哔哩录播文件至网盘。

    输入录播文件所在目录，支持同时处理多个目录。
    """
    asyncio.run(main(dirs_path=dirs_path, config=app.config["CONFIG"], **flags))


@cli.command()
def run():
    """Startup APIFlask APP"""
    print(app.url_map)

    app.run(port=6699, use_reloader=False)


if __name__ == "__main__":
    # Can't interrupt by keyboard
    # t = threading.Thread(target=cli)
    # t.start()
    sys.exit(cli())


# def record_loop(loop_on):
#     try:
#         while True:
#             if loop_on.value == True:
#                 print("loop running")
#             time.sleep(10)
#     except KeyboardInterrupt:
#         print(123)


# if __name__ == "__main__":
#     recording_on = Value("b", True)
#     p = Process(target=record_loop, args=(recording_on,))
#     p.start()
#     app.run(debug=True, use_reloader=False)
#     p.join()
