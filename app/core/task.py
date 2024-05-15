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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .session import Session
from .utils import find_suffix_files


class Task:
    def __init__(self, config: Dict[str, Any], **flags: bool):
        self.tools: Dict[str, Dict[str, Any]] = config["tools"]
        self.flags: Dict[str, bool] = flags

    async def gen_recording_web(self, dir_path: Path):
        """判断并改正目录或文件路径"""
        pass

    async def gen_recording(self, dir_path: Path):
        print("Generating:", dir_path)

        flv_files = find_suffix_files(dir_path, "*.flv")
        m3u8_files = find_suffix_files(dir_path, "*.m3u8")
        mp4_files = find_suffix_files(dir_path, "*.mp4")
        [
            mp4_files.remove(mp4)
            for mp4 in mp4_files[:]
            for file in [*flv_files, *m3u8_files]
            if mp4.stem == file.stem
        ]
        video_files = sorted(
            # 由于 blrec 的行为是当下一个 m3u8 文件创建时，上一个 m3u8 文件才开始转换为 mp4 文件
            # 这将会导致上一个转换后的 mp4 文件的创建时间后于下一个 m3u8 文件的创建时间
            # [*flv_files, *m3u8_files, *mp4_files], key=lambda f: f.stat().st_ctime
            [*flv_files, *m3u8_files, *mp4_files]
        )

        if len(video_files) == 0:
            print(f"No video in {dir_path}, skip!")
            return

        session = Session(self.tools, dir_path / "ALL")
        await session.add_videos(video_files)

        if self.flags["preparation"] or self.flags["all"]:
            await session.gen_preparation()

        if self.flags["early_video"] or self.flags["all"]:
            await session.gen_early_video()
        # if RESULTS.upload:
        #     asyncio.run(session.upload_aDrive())
        # if RESULTS.danmaku_video or RESULTS.all:
        #     asyncio.run(session.gen_danmaku_video())
