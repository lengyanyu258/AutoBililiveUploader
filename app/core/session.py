import argparse
import asyncio
import json
import os
import platform
import re
import subprocess as sp
import sys
import time
import traceback
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from pathlib import Path, PurePath
from pprint import pprint
from typing import Any, Dict, List, Optional, Tuple

from .utils import async_wait_output, ensure_same_anchor
from .video import Video, VideoMeta, VideoType


class Session:
    __upload = False

    @dataclass(init=False)
    class _OutputPaths:
        __OUTPUT_MARK = "ALL"
        __OUTPUT_CACHE_MARK = "cache"

        #
        concat_videos: List[List[Path]] = field(default_factory=list)
        concat_early_videos: List[Tuple[Path, Path]] = field(default_factory=list)
        # danmakus: List[Path | Decimal] = []

        def __init__(self, output_dir: Path) -> None:
            self.__dir = output_dir
            self.base_stem = self.__OUTPUT_MARK

            self.__cache_dir = output_dir / self.__OUTPUT_CACHE_MARK
            self.__cache_dir.mkdir(parents=True, exist_ok=True)

            cache_stem = self.__cache_dir / self.__OUTPUT_MARK
            self.clean_xml: Optional[Path] = cache_stem.with_name("clean.xml")
            self.concat_file = cache_stem.with_name("concat.txt")
            self.extras_log = cache_stem.with_name("extras.log")
            self.he_graph = cache_stem.with_name("he.png")
            self.he_pos = cache_stem.with_name("he_pos.txt")
            self.he_range = cache_stem.with_name("he_range.txt")
            self.sc_srt = cache_stem.with_name("SC.srt")
            self.temp_ps1 = cache_stem.with_name("temp.ps1")
            self.video_log = cache_stem.with_name("video.log")

        @property
        def dir(self):
            return self.__dir

        @property
        def cache_dir(self):
            return self.__cache_dir

        @property
        def base_stem(self):
            return self.__stem

        @base_stem.setter
        def base_stem(self, base_stem: str):
            self.__stem = base_stem
            stem = self.dir / base_stem

            self.thumbnail = stem.with_suffix(".thumbnail.png")
            # 所有视频合并成一个
            self.early_video = stem.with_name(f"【ALL】{stem.stem}.mp4")
            self.danmaku_video = stem.with_name(f"【弹幕高能版】{stem.stem}.mp4")
            self.ass = stem.with_suffix(".ass")
            self.xml: Optional[Path] = stem.with_suffix(".xml")
            self.sc_file = stem.with_suffix(".SC.txt")
            self.he_file = stem.with_suffix(".高能.txt")

    def __init__(self, tools: Dict[str, Dict[str, Any]], output_dir: Path):
        self.__ffmpeg: str = tools["ffmpeg"]["cli"] or "ffmpeg"
        self.__ffprobe: str = tools["ffprobe"]["cli"] or "ffprobe"
        self.__DanmakuFactory: str = tools["DanmakuFactory"]["cli"] or "DanmakuFactory"

        self.__output_paths = self._OutputPaths(output_dir)

        self.__videos: List[Video] = []

        self.__rez_x: int = 1920
        self.__rez_y: int = 1080
        self.__he_time: Optional[Decimal] = None

    async def __query_meta(self, video_path: Path, force: bool = False):
        if force:
            cache_path = self.__output_paths.cache_dir / video_path.name

            input_path, output_path = ensure_same_anchor(
                self.__ffmpeg,
                video_path,
                cache_path,
            )

            await async_wait_output(
                f'{self.__ffmpeg} -y -i "{input_path}" -c copy "{output_path}" >> "{self.__output_paths.video_log}" 2>&1'
            )

            video_path = cache_path

        (video,) = ensure_same_anchor(self.__ffprobe, video_path)

        out, err = await async_wait_output(
            f"{self.__ffprobe} -v error -show_entries format=duration"
            f" -show_entries stream=avg_frame_rate,bit_rate,width,height"
            f' -of json "{video}"'
        )

        if len(err):
            print(f"Something wrong when query {video_path.as_posix()!r} meta, error:")
            print(err.decode())

        data: Dict[str, Any] = json.loads(out)
        video_stream: Dict[str, str] = data["streams"][0]
        audio_stream: Dict[str, str] = data["streams"][1]

        return VideoMeta(
            duration=Decimal(data["format"]["duration"]),
            avg_frame_rate=Fraction(video_stream["avg_frame_rate"]),
            video_bit_rate=int(video_stream["bit_rate"]),
            audio_bit_rate=int(audio_stream["bit_rate"]),
            width=int(video_stream["width"]),
            height=int(video_stream["height"]),
            resolution=f'{video_stream["width"]}x{video_stream["height"]}',
        )

    async def __get_video_meta(self, path: Path):
        try:
            return await self.__query_meta(path)
        except (KeyError, ZeroDivisionError):
            print(f"Video {path} corrupted:")
            print(traceback.format_exc())
            return None

    async def __get_video(self, file: Path):
        video = Video(file=file)
        video.meta = await self.__get_video_meta(video.path)

        if video.m3u8_parts is not None:
            tasks: List[asyncio.Task] = []
            async with asyncio.TaskGroup() as tg:
                for i, m3u8_part in enumerate(video.m3u8_parts):
                    part_file = (
                        self.__output_paths.cache_dir
                        / f"{video.path.stem}.p{i + 1}{video.path.suffix.lower()}"
                    )
                    m3u8_part.path = part_file
                    tasks.append(tg.create_task(self.__get_video_meta(part_file)))
            for i, task in enumerate(tasks):
                video.m3u8_parts[i].meta = task.result()
                m3u8_meta = video.m3u8_parts[i].meta
                print(m3u8_meta)
                print(i, video.m3u8_parts[i].sequence)
                if m3u8_meta is not None:
                    print(m3u8_meta.duration)
                print(video.m3u8_parts[i].duration)

        return video

    def __get_concat_videos(self, separate_concat: bool = False):
        concat_videos: List[List[Path]] = []

        videos: List[Path] = []
        last: Optional[Video] = None
        for this in self.__videos:
            if this.meta is None:
                if len(videos) != 0:
                    concat_videos.append(videos)
                concat_videos.append([this.path])
                videos = []
                last = None
                continue

            if (
                last is not None
                and last.meta is not None
                and this.meta.resolution != last.meta.resolution
            ):
                concat_videos.append(videos)
                videos = [this.path]
                last = this
                continue

            if this.m3u8_parts is None:
                # 当前视频未检测到 m3u8 文件的断流
                if last is None or last.m3u8_parts is None:
                    videos.append(this.path)
                else:
                    # 上个视频文件有断流情况发生
                    if separate_concat:
                        # 若要将断流的最后一 Part 与当前视频合并
                        if (
                            last.m3u8_parts[-1].meta is None
                            or last.m3u8_parts[-1].duration < 12
                        ):
                            videos.append(this.path)
                        else:
                            # 实测这种 concat 之间仍有停顿
                            last_path = videos.pop()
                            concat_videos.append(videos)
                            videos = [last_path, this.path]
                    else:
                        concat_videos.append(videos)
                        videos = [this.path]
            else:
                # 当前视频检测到了 m3u8 文件的断流
                if last is None:
                    videos.extend([part.path for part in this.m3u8_parts])
                else:
                    if last.m3u8_parts is None:
                        # 上个视频文件无断流情况发生
                        if separate_concat:
                            # 若要将断流的第一个 Part 与上个视频合并
                            if (
                                this.m3u8_parts[0].meta is None
                                or this.m3u8_parts[0].duration < 12
                            ):
                                concat_videos.append(videos)
                                m3u8_parts = this.m3u8_parts
                            else:
                                # 实测这种 concat 之间仍有停顿
                                videos.append(this.m3u8_parts[0].path)
                                concat_videos.append(videos)
                                m3u8_parts = this.m3u8_parts[1:]
                        else:
                            # 若不合并，可能会在断流视频开头黑屏（画面信息在上个视频末尾）
                            concat_videos.append(videos)
                            m3u8_parts = this.m3u8_parts
                        videos = [part.path for part in m3u8_parts]
                    else:
                        if (
                            last.m3u8_parts[-1].sequence[-1] + 1
                            == this.m3u8_parts[0].sequence[0]
                        ):
                            videos.extend([part.path for part in this.m3u8_parts])
                        else:
                            concat_videos.append(videos)
                            videos = [part.path for part in this.m3u8_parts]
            last = this
        concat_videos.append(videos)

        pprint(concat_videos)
        return concat_videos

    async def __get_resolution(self):
        resolutions = [
            (v.meta.width, v.meta.height) for v in self.__videos if v.meta is not None
        ]  # prioritize wider, higher-res format

        if len(resolutions) == 0:
            latest = self.__videos[-1]
            latest.meta = await self.__query_meta(latest.path, force=True)
            return latest.meta.width, latest.meta.height

        return max(resolutions)

    async def add_videos(self, files: List[Path]):
        tasks: List[asyncio.Task] = []
        async with asyncio.TaskGroup() as tg:
            for file in files:
                tasks.append(tg.create_task(self.__get_video(file)))
        self.__videos = [task.result() for task in tasks]

        self.__output_paths.base_stem = self.__videos[0].path.stem
        self.__output_paths.concat_videos = self.__get_concat_videos(True)
        self.__rez_x, self.__rez_y = await self.__get_resolution()

    async def __merge_xml(self):
        if self.__output_paths.xml is None:
            return

        xmls = [v.xml.as_posix() for v in self.__videos if v.xml is not None]

        if len(xmls) == 0:
            print("No xmls.")
            self.__output_paths.xml = None
            return
        elif len(xmls) == 1:
            print("No need to merge xmls.")
            self.__output_paths.xml = Path(xmls.pop())
            return

        # In case for too long command
        self.__output_paths.temp_ps1.write_text(data="\n".join(xmls), encoding="utf-8")

        await async_wait_output(
            f"python -m danmaku_tools.merge_danmaku"
            f' "{self.__output_paths.temp_ps1}"'
            f" --offset_time -6"
            # f' --video_time ".{EXT}"'
            f' --output "{self.__output_paths.xml}"'
            f' >> "{self.__output_paths.extras_log}" 2>&1'
        )

    async def __clean_xml(self):
        await self.__merge_xml()

        if self.__output_paths.xml is None:
            self.__output_paths.clean_xml = None
            return
        elif not self.__output_paths.xml.exists():
            print("xml file not exists.")
            self.__output_paths.clean_xml = None
            return

        await async_wait_output(
            f"python -m danmaku_tools.clean_danmaku"
            f' "{self.__output_paths.xml}"'
            f' --output "{self.__output_paths.clean_xml}"'
            f' >> "{self.__output_paths.extras_log}" 2>&1'
        )

    async def __process_xml(self):
        await self.__clean_xml()

        if self.__output_paths.clean_xml is None:
            return
        elif not self.__output_paths.clean_xml.exists():
            print("clean xml file not exists.")
            return

        width_multiple = 1920 // 60

        await async_wait_output(
            f"python -m danmaku_tools.danmaku_energy_map"
            f' --graph "{self.__output_paths.he_graph}"'
            f" --graph_figsize {width_multiple} 1"
            f" --graph_dpi {self.__rez_x // width_multiple}"
            f" --graph_heat_color 5ba691"
            f" --graph_normal_color 91d2be"
            f' --he_map "{self.__output_paths.he_file}"'
            f' --sc_list "{self.__output_paths.sc_file}"'
            f' --he_time "{self.__output_paths.he_pos}"'
            f' --sc_srt "{self.__output_paths.sc_srt}"'
            f' --he_range "{self.__output_paths.he_range}"'
            f' "{self.__output_paths.clean_xml}"'
            f' >> "{self.__output_paths.extras_log}" 2>&1'
        )

        if os.stat(self.__output_paths.sc_srt).st_size == 0:
            print("There is no SC content!")
            os.remove(self.__output_paths.sc_srt)
            os.remove(self.__output_paths.sc_file)

        try:
            with open(self.__output_paths.he_pos, "r") as file:
                he_time_str = file.readline()
                self.__he_time = Decimal(he_time_str)
        except FileNotFoundError as e:
            print(e)
            print("Maybe there is no danmuku & no need to generate danmuku video.")

    async def __process_danmaku(self):
        if self.__output_paths.clean_xml is None:
            return

        font_size = max(self.__rez_x, self.__rez_y) * 36 // 1920
        msgboxfontsize = max(self.__rez_x, self.__rez_y) * 28 // 1920
        print(f"font_size: {font_size}")

        clean_xml, ass = ensure_same_anchor(
            self.__DanmakuFactory,
            self.__output_paths.clean_xml,
            self.__output_paths.ass,
        )

        await async_wait_output(
            f"{self.__DanmakuFactory}"
            f" --ignore-warnings"
            f' -i xml "{clean_xml}"'
            f' -o ass "{ass}"'
            f""
            f" --resolution {self.__rez_x}x{self.__rez_y}"
            f" --scrolltime 12 --fixtime 5 --density 0"
            f""
            f' --fontsize {font_size} --fontname "Sarasa Gothic SC"'
            f" --opacity 255 --outline 1 --shadow 0 --bold TRUE"
            f" --displayarea 1.0 --scrollarea 1.0"
            f""
            f" --showusernames FALSE --showmsgbox TRUE"
            f" --msgboxsize {self.__rez_x // 6 - 10}x{self.__rez_y - 10}"
            f" --msgboxpos 5x5"
            f" --msgboxfontsize {msgboxfontsize}"
            f" --msgboxduration 0.00"
            f" --giftminprice 0.00"
            # f" --giftminprice 6.60"  # “干杯”：66 电池
            f" --giftmergetolerance 0.00"
            # f" --giftmergetolerance 5"  # 合并 5 秒内的礼物信息
            f' >> "{self.__output_paths.extras_log}" 2>&1'
        )

    async def __gen_thumbnail(self, video_path: Path, he_time: Decimal, png_path: Path):
        video, png = ensure_same_anchor(self.__ffmpeg, video_path, png_path)

        await async_wait_output(
            f'{self.__ffmpeg} -y -ss {he_time} -i "{video}" -vframes 1 -q:v 1 "{png}"'
            f' >> "{self.__output_paths.video_log}" 2>&1'
        )

    async def __process_thumbnail(self):
        if self.__he_time is None:
            print("No he_time.")
            return

        local_he_time = self.__he_time

        thumbnail_generated = False

        for video in self.__videos:
            if video.meta is None:
                video.meta = await self.__query_meta(video.path, force=True)

            if local_he_time < video.meta.duration:
                await self.__gen_thumbnail(
                    video.path, local_he_time, self.__output_paths.thumbnail
                )
                thumbnail_generated = True
                break
            local_he_time -= video.meta.duration

        if not thumbnail_generated:  # Rare case where he_pos is after the last video
            print(f'"{self.__videos}": thumbnail at {local_he_time} cannot be found.')
            if self.__videos[-1].meta is None:
                self.__videos[-1].meta = await self.__query_meta(
                    self.__videos[-1].path, force=True
                )
            await self.__gen_thumbnail(
                self.__videos[-1].path,
                self.__videos[-1].meta.duration / 2,
                self.__output_paths.thumbnail,
            )

    async def gen_preparation(self):
        await self.__process_xml()
        await self.__process_danmaku()
        await self.__process_thumbnail()

    def __generate_concat(self, videos: List[Path], concat_file: Path):
        files = ensure_same_anchor(self.__ffmpeg, *videos)
        text = "\n".join([f"file '{path}'" for path in files])
        concat_file.write_text(text, encoding="utf-8")

    async def __process_early_video(
        self, concat_videos: List[Path], concat_early_videos: Tuple[Path, Path]
    ):
        concat_file, concat_early_video = concat_early_videos

        if concat_early_video.exists():
            print(f"{concat_early_video} exists, skip!")
            return

        self.__generate_concat(concat_videos, concat_file)

        input_path, output_path = ensure_same_anchor(
            self.__ffmpeg, concat_file, concat_early_video
        )

        await async_wait_output(
            f"{self.__ffmpeg} -y"
            f" -f concat -safe 0"
            f' -i "{input_path}"'
            f" -codec copy"
            f" -bsf:v filter_units=remove_types=12"
            f' "{output_path}"'
            f' >> "{self.__output_paths.video_log}" 2>&1'
        )

    async def gen_early_video(self):
        if len(self.__videos) == 1:
            if self.__videos[0].type is VideoType.MP4:
                self.__output_paths.early_video = self.__videos[0].path
                print("No need to process early video.")
                return

        if len(self.__output_paths.concat_videos) == 1:
            self.__output_paths.concat_early_videos = [
                (self.__output_paths.concat_file, self.__output_paths.early_video)
            ]
            await self.__process_early_video(
                self.__output_paths.concat_videos[0],
                self.__output_paths.concat_early_videos[-1],
            )
            return

        self.__output_paths.concat_early_videos = []
        for concat_videos in self.__output_paths.concat_videos:
            base_stem = concat_videos[0].stem

            concat_file = self.__output_paths.cache_dir / f"{base_stem}.concat.txt"
            concat_early_video = self.__output_paths.dir / f"{base_stem}.mp4"

            self.__output_paths.concat_early_videos.append(
                (concat_file, concat_early_video)
            )

            # ffmpeg 会跑满磁盘，故此处不必进行多协程并行
            await self.__process_early_video(
                concat_videos, self.__output_paths.concat_early_videos[-1]
            )

    async def __process_video(self):
        early_video, danmaku_video, ass = ensure_same_anchor(
            self.__ffmpeg,
            self.__output_paths.early_video,
            self.__output_paths.danmaku_video,
            self.__output_paths.ass,
        )

        # TODO: 将视频拆分为三份(1060显卡的上限)并行渲染
        # **当 input 为 mp4 时，ffmpeg 能跑满显卡，所以不用拆分了。
        gop = 5  # set GOP = 5s

        if self.__output_paths.early_video.exists():
            early_video_meta = await self.__query_meta(self.__output_paths.early_video)

            total_time = early_video_meta.duration
            avg_fps = early_video_meta.avg_frame_rate
            # avg_bitrate = float(json_data["streams"][0]["bit_rate"]) / 1000  # Kbps
            # "bit_rate": "255936"
            audio_bit_rate = early_video_meta.audio_bit_rate / 1000

            # 使用 mp4 文件能显著提升压制速度（占满显卡）
            input_video = f' -i "{early_video}"'
        else:
            if len(self.__output_paths.concat_early_videos) > 0:
                # 已进行过视频文件合并
                concat_early_videos = map(
                    lambda l: l[-1], self.__output_paths.concat_early_videos
                )

                tasks: List[asyncio.Task] = []
                async with asyncio.TaskGroup() as tg:
                    for concat_early_video in concat_early_videos:
                        tasks.append(
                            tg.create_task(self.__query_meta(concat_early_video))
                        )
                early_videos_meta: List[VideoMeta] = [task.result() for task in tasks]

                for meta in early_videos_meta:
                    # 判断分辨率是否相同
                    if (meta.width, meta.height) != (self.__rez_x, self.__rez_y):
                        await async_wait_output(
                            f"{self.__ffmpeg}"
                            f' -File "{temp_ps1}"'
                            f" -ExecutionPolicy Bypass"
                            f' >> "{self.__output_paths.video_log}" 2>&1'
                        )

                total_time = sum([meta.duration for meta in early_videos_meta])
                avg_fps = sum(
                    [meta.avg_frame_rate for meta in early_videos_meta]
                ) / len(early_videos_meta)
                audio_bit_rate = (
                    sum([meta.audio_bit_rate for meta in early_videos_meta])
                    / len(early_videos_meta)
                    / 1000
                )
            else:
                pass
            # avg_bitrate = float(
            #     sum([video.video_bit_rate for video in self.videos])
            #     / len(self.videos)
            #     / 1000
            # )  # Kbps

            input_video = (
                f"-f concat -safe 0 -i \"{self.__output_paths['concat_file']}\""
            )

        if (
            len(self.__videos) > 1
            and any(v.type for v in self.__videos) is VideoType.FLV
        ):
            start_time = os.stat(self.__videos[0]._path).st_ctime
            end_time = os.stat(self.__videos[-1]._path).st_mtime
            real_total_time = end_time - start_time
            percentage = Decimal(total_time / real_total_time * 100).quantize(
                Decimal("1.00"), rounding="ROUND_HALF_UP"
            )
            print(f"time ratio: {percentage}%")
            if total_time < real_total_time:
                lacked_time = time.gmtime(real_total_time - total_time)
                print(f"lacked time: {time.strftime('%M分%S秒', lacked_time)}")
            print()

        # BiliBili now re-encode every video anyways
        max_video_bitrate = float(8_000)  # Kbps

        # 如果需要完整上传 B 站
        # max_size = 32 * 1024 * 1024 * 8  # 32GB
        max_size = 8 * 1024 * 1024 * 1024 * 8 / 1000  # Kb(internet)
        # min_video_bitrate = float(6000)  # for 1080p, see uploader webpage tips
        # <del>由于网页端限制的 8G = 8192 M > 8e9 B ≈ 7,629 MiB 且有充足的裕量，
        # 故不必针对 audio bitrate & muxing overhead 作出修正</del>
        # 由于有 bufsize = video_bitrate * 2，足以产生一些裕量，
        # 故不必针对 muxing overhead 作出修正
        video_bitrate = int(max_size / total_time - audio_bit_rate)  # Kbps
        # NVENC 和 QSV 半斤八两，达到 X264 的质量需要增加 30% 的码率。(Ref: https://zhuanlan.zhihu.com/p/78829414)
        # 但由于增加了弹幕因素，所以在原视频码率的基础上需要更多的码率
        # 然而每个视频的弹幕或多或少无法估计，所以这里一股脑采用“极限”码率
        # TODO: 使用弹幕字数来估计需要用到的码率（接近为 0 时为 1.3 倍码率）
        # 或者是试试直接用原码率进行 HEVC 的编码。
        # min_video_bitrate = min(max_video_bitrate, video_bitrate, int(avg_bitrate * 1.3))
        min_video_bitrate = min(max_video_bitrate, video_bitrate)
        # 如果使用在大小限制下的“极限”码率，则禁用 -maxrate 选项
        if min_video_bitrate == video_bitrate:
            max_video_bitrate = min_video_bitrate
        video_bitrate = min_video_bitrate

        filter_complex = f"""
            [1:v]scale={self.__rez_x}:{self.__rez_y}:force_original_aspect_ratio=decrease,pad={self.__rez_x}:{self.__rez_y}:-1:-1:color=black[v_fixed];
            [0:v][v_fixed]scale2ref=iw:iw*(main_h/main_w)[color][ref];
            [color]split[color1][color2];
            [color1]hue=s=0[gray];
            [color2]negate=negate_alpha=1[color_neg];
            [gray]negate=negate_alpha=1[gray_neg];
            color=black:d={total_time}[black];
            [black][ref]scale2ref[blackref][ref2];
            [blackref]split[blackref1][blackref2];
            [color_neg][blackref1]overlay=x=t/{total_time}*W-W[color_crop_neg];
            [gray_neg][blackref2]overlay=x=t/{total_time}*W[gray_crop_neg];
            [color_crop_neg]negate=negate_alpha=1[color_crop];
            [gray_crop_neg]negate=negate_alpha=1[gray_crop];
            [ref2][color_crop]overlay=y=main_h-overlay_h[out_color];
            [out_color][gray_crop]overlay=y=main_h-overlay_h[out];
            [out]ass='{ass}'[out_sub]
        """
        filter_complex = filter_complex.replace("\n", "")

        output_video_options = (
            f" -preset p3 -cq 28"
            if RESULTS.no_limit
            else f" -preset slow"
            f" -b:v {video_bitrate}K -maxrate:v {max_video_bitrate}K -bufsize:v {video_bitrate * 2}K"
        )
        ffmpeg_command = (
            f"ffmpeg -y"
            f" -t {total_time}"
            f" -i \"{self.__output_paths['he_graph']}\""
            f" {input_video}"
            f" -t {total_time}"
            f' -filter_complex "{filter_complex}" -map "[out_sub]" -map 1:a'
            f" -c:v h264_nvenc {output_video_options}"
            f" -profile:v high -rc vbr -rc-lookahead 32 -temporal-aq 1"
            f" -coder cabac -bf 3 -b_ref_mode middle -multipass fullres"
            f" -qmin 0 -g {int(avg_fps * gop)}"
            f' -c:a copy "{danmaku_video}"'
            # f' >> "{self.output_paths["video_log"]}" 2>&1'
        )

        self.__output_paths.temp_ps1.write_text(
            f"Measure-Command {{ {ffmpeg_command} | Out-Host }}", encoding="gb18030"
        )

        (temp_ps1,) = ensure_same_anchor("PowerShell.exe", self.__output_paths.temp_ps1)

        # print(powershell_command)
        # sp.run(powershell_command, shell=True, check=True)
        await async_wait_output(
            f"PowerShell.exe"
            f' -File "{temp_ps1}"'
            f" -ExecutionPolicy Bypass"
            f' >> "{self.__output_paths.video_log}" 2>&1'
        )

    async def gen_danmaku_video(self):
        await self.__process_video()
        if self.__upload:
            danmaku_video = self.__output_paths["danmaku_video"].replace(
                self.__drive, self.__anchor
            )
            upload_command = (
                f"aliyunpan upload"
                f' "{danmaku_video}"'
                f' "{(self.__drive_dir / self.__new_dirname.name).as_posix()}"'
                f' >> "{self.__output_paths.extras_log}" 2>&1'
            )
            await async_wait_output(upload_command)

    async def upload_aDrive(self):
        self.__upload = True
        early_video = Path(self.__output_paths["early_video"])
        old_dirname = early_video.parent.parent
        # TODO: 有 Danmaku 时文件夹名称添加 with Danmaku 后缀
        new_dirname = old_dirname.parent / f"{old_dirname.name} [Auto upload]"
        early_video.parent.rename(new_dirname)
        self.__new_dirname = new_dirname
        self.__gen_output_paths(new_dirname)
        parent_dir = new_dirname.parent
        drive_dir = PurePath("/", parent_dir.parent.name, parent_dir.name)
        self.__drive_dir = drive_dir
        escaped_mark = self.__OUTPUT_CACHE_MARK.replace(".", "\\.")
        # --ow 需要已存在同名文件
        upload_command = (
            f"aliyunpan upload --norapid"
            f' -exn "{escaped_mark}.+$"'
            f' "{new_dirname.as_posix()}"'
            f' "{drive_dir.as_posix()}"'
            f' >> "{self.__output_paths["extras_log"]}" 2>&1'
        )
        # aliyunpan 本身具有计时功能
        await async_wait_output(upload_command)

        upload_command = (
            f"BaiduPCS-Go upload --norapid --policy overwrite"
            # f" --norapid --nosplit"
            f' "{old_dirname.as_posix()}"'
            f' "{drive_dir.as_posix()}"'
            f' >> "{self.__output_paths["extras_log"]}" 2>&1'
        )
        # BaiduPCS-Go 本身具有计时功能
        await async_wait_output(upload_command)
