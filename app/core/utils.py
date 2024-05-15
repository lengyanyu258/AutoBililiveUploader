import argparse
import asyncio
import decimal
import json
import logging
import os
import platform
import subprocess as sp
import sys
import time
import traceback
from pathlib import Path, PosixPath, PurePath, WindowsPath
from typing import Any, Dict, List, Optional, Tuple

import requests


async def async_wait_output(command):
    print(f"{time.ctime(time.time())}, running: {command}\n")
    sys.stdout.flush()
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    return_value = await process.communicate()
    sys.stdout.flush()
    sys.stderr.flush()
    return return_value


def find_suffix_files(dir_path: Path, pattern: str):
    stem, suffix = pattern.rsplit(".", maxsplit=1)
    suffix_pattern = ""
    for i in suffix:
        if (u := i.upper()) == (l := i.lower()):
            suffix_pattern += i
        else:
            suffix_pattern += f"[{u}{l}]"
    return list(dir_path.glob(f"{stem}.{suffix_pattern}"))


def find_suffix_file(dir_path: Path, pattern: str):
    files = find_suffix_files(dir_path, pattern)
    if len(files) == 0:
        return None
    return files.pop()


def ensure_same_anchor(exe: str, *files: Path):
    """确保文件路径与可执行文件相匹配

    Args:
        `exe` (str): 可执行文件路径或需要转换成的目标系统
        `*files` (Path): 已存在的文件，Windows 文件为 `WindowsPath`，否则为 `PosixPath`

    Returns:
        `list[str]`: 被转换后的系列 Posix 风格的 `*files` 字符串路径
    """
    paths: List[str] = []
    if exe.lower().endswith(".exe"):
        for file in files:
            if isinstance(file, PosixPath):
                paths.append(f"{file.parts[2].upper()}:/" + "/".join(file.parts[3:]))
            else:
                paths.append(file.as_posix())
    else:
        for file in files:
            if isinstance(file, WindowsPath):
                paths.append(
                    f"/mnt/{file.drive[:-1].lower()}/" + "/".join(file.parts[1:])
                )
            else:
                paths.append(file.as_posix())

    return paths


def load_cookies(cookies_fn):
    with open(cookies_fn, "rt") as f:
        cookie_list = json.load(f)["cookie_info"]["cookies"]
    return {i["name"]: i["value"] for i in cookie_list}


def load_cookie_str(cookies_fn):
    cookies = [f"{i}={v}" for i, v in load_cookies(cookies_fn).items()]
    return "; ".join(cookies)


def check_cookies(cookies_fn, retries=5):
    cookies = load_cookies(cookies_fn)
    print(cookies)
    r = requests.get(
        "http://api.vc.bilibili.com/session_svr/v1/session_svr/single_unread",
        cookies=cookies,
        timeout=10,
    )
    if r.json()["code"] != 0:
        raise ValueError("%s %s %s" % (cookies_fn, cookies["DedeUserID"], r.text))
    else:
        print(r.json())


def update_mikurec_cookies(url, headers={}, fn="cookies.json"):
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        current = r.json()
        current["optionalCookie"] = {
            "hasValue": True,
            "value": load_cookies(cookies_fn=fn),
        }
        r = requests.post(url, json=current, headers=headers)
        print(r)
        print(r.json())


def update_blrec_cookies(url, headers={"X-API-KEY": ""}, fn="cookies.json"):
    r = requests.patch(
        url,
        headers=headers,
        json={"header": {"cookie": load_cookie_str(cookies_fn=fn)}},
    )
    print(r)
    print(r.json())


if __name__ == "__main__":
    cookies_fn = "/home/shawn/.config/biliup/cookies.json"
    # print('check_cookies:')
    # check_cookies(cookies_fn)
    # print('load_cookie_str:')
    # print(load_cookie_str(cookies_fn))
    # update_mikurec_cookies('https://rec.example.org/api/config/global', headers={'Authorization': 'Basic dXNlcj1wYXNzd2Q='}, fn=cookies_fn)
    print("update_blrec_cookies:")
    update_blrec_cookies("http://localhost:2233/api/v1/settings", fn=cookies_fn)
