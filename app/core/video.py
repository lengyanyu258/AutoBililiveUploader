import argparse
import asyncio
import json
import os
import platform
import subprocess as sp
import sys
import time
import traceback
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import m3u8

from .utils import find_suffix_file


class VideoType(StrEnum):
    FLV = ".flv"
    M3U8 = ".m3u8"
    MP4 = ".mp4"


@dataclass
class VideoMeta:
    duration: Decimal
    avg_frame_rate: Fraction
    video_bit_rate: int
    audio_bit_rate: int
    width: int
    height: int
    resolution: str


def get_sequence_number(m3u8_segment: m3u8.Segment):
    return int(str(m3u8_segment.title).rsplit("|", 1)[-1].split(".")[0])


@dataclass(init=False)
class VideoM3U8:
    """VideoM3U8 Dataclass

    - `m3u8_obj`：`m3u8` 视频对象
    """

    # 轻度文件健康程度检测标志
    meta: Optional[VideoMeta] = None

    def __init__(self, obj: m3u8.M3U8) -> None:
        self.m3u8_obj = obj

    @property
    def m3u8_obj(self):
        return self.__m3u8

    @m3u8_obj.setter
    def m3u8_obj(self, obj: m3u8.M3U8):
        self.__m3u8 = obj

        self.duration = sum(
            [Decimal(str(seg.duration)) for seg in obj.segments], start=0
        )
        self.sequence: Tuple[int, int] = (
            get_sequence_number(obj.segments[0]),
            get_sequence_number(obj.segments[-1]),
        )

    @property
    def path(self):
        return self.__path

    @path.setter
    def path(self, file: Path):
        self.__path = file

        # TODO: 默认为当前路径下的子目录，需考虑分散在不同目录下的情况，比如使用绝对路径，每次重新对 path 赋值，或是更聪明地使用相对路径
        layers = len(file.relative_to(f"{self.m3u8_obj.base_uri!s}").parts) - 1
        for segment in self.m3u8_obj.segments:
            segment.uri = f"{'../' * layers}{segment.uri}"
            if segment.init_section is not None:
                segment.init_section.uri = segment.uri

        # 若目录不存在则会自动创建目录
        self.m3u8_obj.dump(file.as_posix())


class Video:
    """已存在的视频文件

    - `file`：视频文件的路径，包含 `flv`，`m3u8`，`mp4` 格式
    """

    def __init__(self, file: Path):
        # Ensure we have the Drive part.
        self.path = file.resolve(strict=True)
        self.type = VideoType(file.suffix.lower())
        self.meta: Optional[VideoMeta] = None

        self.m3u8_parts: Optional[List[VideoM3U8]] = self.__get_m3u8_parts()

        # TODO: 支持弹幕时间为负数，即直接在屏幕中直接出现
        # Duration: sum(xml) ~ sum(mp4)
        self.xml: Optional[Path] = find_suffix_file(file.parent, f"{file.stem}.xml")
        # self.jsonl: Optional[Path] = find_suffix_file(path.parent, f"{path.stem}.jsonl")

    # 由于有时网络不稳定导致的断流使得 sequence number 回退而视频画面不会退，故此处不需要裁剪
    # def __clip_m3u8(self, obj: m3u8.M3U8, last_sequence: int):
    #     m3u8_obj = m3u8.M3U8(base_uri=obj.base_uri)
    #     for segment in obj.segments:
    #         if get_sequence_number(segment) > last_sequence:
    #             m3u8_obj.add_segment(segment)
    #     return m3u8_obj

    def __get_m3u8_parts(self):
        if self.type is not VideoType.M3U8:
            return None

        m3u8_file = m3u8._load_from_file(self.path.as_posix())
        discontinuity = False

        m3u8_parts: List[VideoM3U8] = []
        m3u8_obj = m3u8.M3U8(base_uri=self.path.parent.as_posix())
        for segment in m3u8_file.segments:
            # segment: m3u8.Segment = segment
            if segment.discontinuity:
                discontinuity = True
                m3u8_parts.append(VideoM3U8(m3u8_obj))
                m3u8_obj = m3u8.M3U8(base_uri=self.path.parent.as_posix())
                segment.discontinuity = False
            m3u8_obj.add_segment(segment)
        m3u8_parts.append(VideoM3U8(m3u8_obj))

        if not discontinuity:
            return None

        # Check sequence numbers
        # for i, m3u8_part in enumerate(m3u8_parts[1:], start=1):
        #     last_end = m3u8_parts[i - 1].sequence[-1]
        #     start, end = m3u8_part.sequence
        #     if start < last_end and end > last_end:
        #         print(last_end, start, end)
        #         m3u8_part.obj = self.__clip_m3u8(m3u8_part.obj, last_end)

        for part in m3u8_parts:
            part.m3u8_obj.version = m3u8_file.version  # type: ignore
            part.m3u8_obj.target_duration = m3u8_file.target_duration  # type: ignore
            part.m3u8_obj.start = m3u8_file.start
            part.m3u8_obj.is_endlist = True  # type: ignore

        return m3u8_parts
