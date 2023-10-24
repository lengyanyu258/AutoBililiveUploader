import os
import sys
import json
import time
import decimal
import pathlib
import asyncio
import platform
import argparse
import traceback
import subprocess as sp
from typing import Optional, List


# Reference: https://github.com/valkjsaaa/auto-bilibili-recorder/blob/master/session.py 2023年6月7日

if platform.system().lower() == "windows":
    BINARY_PATH_DRIVE = pathlib.PurePath("D:/")
    BINARY_PATH_RELATIVE_TO_DRIVE = pathlib.PurePath(
        "Users/Shawn/Source/Repos/lengyanyu258/DanmakuFactory",
    )
    BINARY_PATH_EXE = pathlib.PurePath("bin/DanmakuFactory.exe")
    BINARY_PATH = os.fspath(
        BINARY_PATH_DRIVE / BINARY_PATH_RELATIVE_TO_DRIVE / BINARY_PATH_EXE
    )
else:
    BINARY_PATH = (
        pathlib.Path("~/Github/DanmakuFactory/DanmakuFactory").expanduser().as_posix()
    )


async def async_wait_output(command):
    print(f"running: {command}\n")
    sys.stdout.flush()
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    return_value = await process.communicate()
    sys.stdout.flush()
    sys.stderr.flush()
    return return_value


class Video:
    base_path: str
    video_resolution: str
    video_resolution_x: int
    video_resolution_y: int
    video_duration: float
    video_avg_fps: float
    video_bit_rate: float
    video_file_path: str
    xml_file_path: str

    def __init__(self, video_name: pathlib.Path):
        video_path = video_name.resolve(strict=True)
        self.base_path = os.fspath(video_path.with_suffix(""))
        self.video_file_path = os.fspath(video_path)
        self.xml_file_path = self.base_path + ".xml"

    async def gen_thumbnail(self, he_time, png_file_path, video_log_path):
        ffmpeg_command_img = (
            f'ffmpeg -y -ss {he_time} -i "{self.video_file_path}" -vframes 1 "{png_file_path}"'
            f' >> "{video_log_path}" 2>&1'
        )
        await async_wait_output(ffmpeg_command_img)

    async def query_meta(self):
        video_data_str = await async_wait_output(
            f"ffprobe -v error -show_entries format=duration"
            f" -select_streams v:0 -show_entries stream=avg_frame_rate,bit_rate,width,height"
            f' -of json "{self.video_file_path}"'
        )
        json_data = json.loads(video_data_str[0])

        self.video_duration = float(json_data["format"]["duration"])
        self.video_avg_fps = eval(json_data["streams"][0]["avg_frame_rate"])
        self.video_bit_rate = float(json_data["streams"][0]["bit_rate"])
        self.video_resolution_x = int(json_data["streams"][0]["width"])
        self.video_resolution_y = int(json_data["streams"][0]["height"])
        self.video_resolution = f"{self.video_resolution_x}x{self.video_resolution_y}"


class Session:
    __upload = False
    videos: List[Video]
    he_time: Optional[float]
    output_paths: dict[str, str]
    output_mark: str
    output_cache_mark: str

    def __init__(self):
        self.videos = []
        self.he_time = None
        self.output_paths = {}
        self.output_mark = "ALL"
        self.output_cache_mark = ".cache"

    async def add_video(self, video: Video):
        try:
            await video.query_meta()
        except ValueError:
            print(traceback.format_exc())
            print(f"video corrupted, skipping: {video.video_file_path}\n")
            return
        self.videos += [video]

    def gen_output_paths(self, output_dir: pathlib.Path | None = None):
        output_path = pathlib.Path(
            f"{self.videos[0].base_path.replace('-001','')}-{self.output_mark}"
        )
        if not output_dir:
            output_dir = output_path.parent / self.output_mark
            output_dir.mkdir(parents=False, exist_ok=True)
        output_base_path = os.fspath(output_dir / output_path.name)

        self.output_paths = {
            "ass": output_base_path + ".ass",
            "danmaku_video": output_base_path + ".danmaku_bar.mp4",
            "early_video": output_base_path + ".mp4",
            "he_file": output_base_path + ".he.txt",
            "sc_file": output_base_path + ".sc.txt",
            "sc_srt": output_base_path + ".sc.srt",
            "thumbnail": output_base_path + ".thumb.png",
            "xml": output_base_path + ".xml",
            "clean_xml": f"{output_base_path}{self.output_cache_mark}.clean.xml",
            "concat_file": f"{output_base_path}{self.output_cache_mark}.concat.txt",
            "extras_log": f"{output_base_path}{self.output_cache_mark}.extras.log",
            "he_graph": f"{output_base_path}{self.output_cache_mark}.he.png",
            "he_pos": f"{output_base_path}{self.output_cache_mark}.he_pos.txt",
            "he_range": f"{output_base_path}{self.output_cache_mark}.he_range.txt",
            "temp_ps1": f"{output_base_path}{self.output_cache_mark}.temp.ps1",
            "video_log": f"{output_base_path}{self.output_cache_mark}.video.log",
        }

    async def merge_xml(self):
        # if len(self.videos) <= 1:
        #     self.output_paths["xml"] = self.videos[0].xml_file_path
        #     print("No need to merge xmls.\n")
        #     return

        # In case for too long command
        xmls = "\n".join([video.xml_file_path for video in self.videos])
        with open(self.output_paths["temp_ps1"], "w", encoding="utf-8") as f:
            f.write(xmls)
        danmaku_merge_command = (
            f"python -m danmaku_tools.merge_danmaku"
            f' "{self.output_paths["temp_ps1"]}"'
            f" --offset_time -6"
            f' --video_time ".flv"'
            f" --output \"{self.output_paths['xml']}\""
            f" >> \"{self.output_paths['extras_log']}\" 2>&1"
        )
        await async_wait_output(danmaku_merge_command)

    async def clean_xml(self):
        await self.merge_xml()
        danmaku_clean_command = (
            f"python -m danmaku_tools.clean_danmaku"
            f" \"{self.output_paths['xml']}\""
            f" --output \"{self.output_paths['clean_xml']}\""
            f" >> \"{self.output_paths['extras_log']}\" 2>&1"
        )
        await async_wait_output(danmaku_clean_command)

    async def process_xml(self):
        await self.clean_xml()
        width_multiple = 32
        danmaku_extras_command = (
            f"python -m danmaku_tools.danmaku_energy_map"
            f" --graph \"{self.output_paths['he_graph']}\""
            f" --graph_figsize {width_multiple} 1"
            f" --graph_dpi {self.get_resolution()[0] // width_multiple}"
            f" --graph_heat_color 5ba691"
            f" --graph_normal_color 91d2be"
            f" --he_map \"{self.output_paths['he_file']}\""
            f" --sc_list \"{self.output_paths['sc_file']}\""
            f" --he_time \"{self.output_paths['he_pos']}\""
            f" --sc_srt \"{self.output_paths['sc_srt']}\""
            f" --he_range \"{self.output_paths['he_range']}\""
            f" \"{self.output_paths['clean_xml']}\""
            f" >> \"{self.output_paths['extras_log']}\" 2>&1"
        )
        await async_wait_output(danmaku_extras_command)

        if os.stat(self.output_paths["sc_srt"]).st_size == 0:
            print("There is no SC content!")
            os.remove(self.output_paths["sc_srt"])
            os.remove(self.output_paths["sc_file"])

        try:
            with open(self.output_paths["he_pos"], "r") as file:
                he_time_str = file.readline()
                self.he_time = float(he_time_str)
        except FileNotFoundError as e:
            print(e)
            print("Maybe there is no danmuku & no need to generate danmuku video.")
            exit()

    def generate_concat(self, is_win=False):
        if is_win:
            concat_text = "\n".join(
                [
                    f"file '{video.video_file_path.replace(self.__anchor, self.__drive)}'"
                    for video in self.videos
                ]
            )
        else:
            concat_text = "\n".join(
                [f"file '{video.video_file_path}'" for video in self.videos]
            )

        with open(
            file=self.output_paths["concat_file"], mode="w", encoding="utf-8"
        ) as concat_file:
            concat_file.write(concat_text)

    async def process_thumbnail(self):
        local_he_time = self.he_time
        thumbnail_generated = False
        if local_he_time is not None:
            for video in self.videos:
                if local_he_time < video.video_duration:
                    await video.gen_thumbnail(
                        local_he_time,
                        self.output_paths["thumbnail"],
                        self.output_paths["video_log"],
                    )
                    thumbnail_generated = True
                    break
                local_he_time -= video.video_duration
        if not thumbnail_generated:  # Rare case where he_pos is after the last video
            print(
                f"\"{self.output_paths['video']}\": thumbnail at {local_he_time} cannot be found\n"
            )
            await self.videos[-1].gen_thumbnail(
                self.videos[-1].video_duration / 2,
                self.output_paths["thumbnail"],
                self.output_paths["video_log"],
            )

    def get_resolution(self):
        video_res_sorted = list(
            reversed(
                [
                    (
                        video.video_resolution_x / video.video_resolution_y,
                        video.video_resolution_x,
                        video.video_resolution_y,
                    )
                    for video in self.videos
                ]
            )
        )  # prioritize wider, higher-res format
        video_res_x = video_res_sorted[0][1]
        video_res_y = video_res_sorted[0][2]
        return video_res_x, video_res_y

    async def process_danmaku(self):
        video_res_x, video_res_y = self.get_resolution()
        font_size = max(video_res_x, video_res_y) * 36 // 1920
        msgboxfontsize = max(video_res_x, video_res_y) * 28 // 1920
        print(f"font_size: {font_size}\n")
        danmaku_conversion_command = (
            f"{BINARY_PATH}"
            f" --ignore-warnings"
            f" -i xml \"{self.output_paths['clean_xml']}\""
            f" -o ass \"{self.output_paths['ass']}\""
            f""
            f" --resolution {video_res_x}x{video_res_y}"
            f" --scrolltime 12 --fixtime 5 --density 0"
            f""
            f' --fontsize {font_size} --fontname "Sarasa Gothic SC"'
            f" --opacity 255 --outline 1 --shadow 0 --bold TRUE"
            f" --displayarea 1.0 --scrollarea 1.0"
            f""
            f" --showusernames FALSE --showmsgbox TRUE"
            f" --msgboxsize {video_res_x // 6 - 10}x{video_res_y - 10}"
            f" --msgboxpos 5x5"
            f" --msgboxfontsize {msgboxfontsize}"
            f" --msgboxduration 0.00"
            f" --giftminprice 0.00"
            # f" --giftminprice 6.60"  # “干杯”：66 电池
            f" --giftmergetolerance 0.00"
            # f" --giftmergetolerance 5"  # 合并 5 秒内的礼物信息
            f" >> \"{self.output_paths['extras_log']}\" 2>&1"
        )
        await async_wait_output(danmaku_conversion_command)

    async def process_early_video(self):
        # if len(self.videos) <= 1:
        #     self.output_paths["early_video"] = self.videos[0].video_file_path
        #     print("No need to process early video.\n")
        #     return

        if pathlib.Path(self.output_paths["early_video"]).exists():
            print(f'{self.output_paths["early_video"]} exists, skip!\n')
            return

        ref_video_res = self.videos[0].video_resolution
        for video in self.videos:
            if video.video_resolution != ref_video_res:
                print("format check failed!\n")
                return

        ffmpeg_command = (
            f"ffmpeg -y"
            f" -f concat -safe 0"
            f" -i \"{self.output_paths['concat_file']}\""
            f" -c copy"
            f" \"{self.output_paths['early_video']}\""
            f" >> \"{self.output_paths['video_log']}\" 2>&1"
        )
        await async_wait_output(ffmpeg_command)

    async def process_video(self):
        # TODO: 将视频拆分为三份(1060显卡的上限)并行渲染
        # **当 input 为 mp4 时，ffmpeg 能跑满显卡，所以不用拆分了。
        gop = 5  # set GOP = 5s

        early_video_exists = False
        if os.path.exists(self.output_paths["early_video"]):
            early_video_exists = True
            video_data_str = await async_wait_output(
                f"ffprobe -v error -show_entries format=duration"
                f" -show_entries stream=avg_frame_rate,bit_rate"
                f' -of json "{self.output_paths["early_video"]}"'
            )
            json_data = json.loads(video_data_str[0])

            total_time = float(json_data["format"]["duration"])
            avg_fps = eval(json_data["streams"][0]["avg_frame_rate"])
            # avg_bitrate = float(json_data["streams"][0]["bit_rate"]) / 1000  # Kbps
            # "bit_rate": "255936"
            audio_bit_rate = float(json_data["streams"][1]["bit_rate"]) / 1000
        else:
            total_time = sum([video.video_duration for video in self.videos])
            avg_fps = sum([video.video_avg_fps for video in self.videos]) / len(
                self.videos
            )
            # avg_bitrate = float(
            #     sum([video.video_bit_rate for video in self.videos])
            #     / len(self.videos)
            #     / 1000
            # )  # Kbps
            audio_bit_rate = 320

        if len(self.videos) > 1:
            start_time = os.stat(self.videos[0].video_file_path).st_ctime
            end_time = os.stat(self.videos[-1].video_file_path).st_mtime
            real_total_time = end_time - start_time
            percentage = decimal.Decimal(total_time / real_total_time * 100).quantize(
                decimal.Decimal("1.00"), rounding="ROUND_HALF_UP"
            )
            print(f"time ratio: {percentage}%")
            if total_time < real_total_time:
                lacked_time = time.gmtime(real_total_time - total_time)
                print(f"lacked time: {time.strftime('%M分%S秒', lacked_time)}")
            print()

        # BiliBili now re-encode every video anyways
        # max_video_bitrate = float(8_000)  # Kbps
        # 老千的弹幕并不多，所以码率压低一些（2333，4000 够用了）
        max_video_bitrate = float(4_000)  # Kbps

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

        ass_path = pathlib.PurePath(self.output_paths["ass"])
        self.__anchor = ass_path.parents[-3].as_posix()
        self.__drive = f"{ass_path.parts[2].upper()}:"

        ass_path = ass_path.as_posix().replace(self.__anchor, self.__drive)
        self.output_paths["ass"] = ass_path.replace(":", "\\:")
        self.output_paths["he_graph"] = self.output_paths["he_graph"].replace(
            self.__anchor, self.__drive
        )
        self.output_paths["early_video"] = self.output_paths["early_video"].replace(
            self.__anchor, self.__drive
        )
        self.generate_concat(True)
        self.output_paths["concat_file"] = self.output_paths["concat_file"].replace(
            self.__anchor, self.__drive
        )
        self.output_paths["danmaku_video"] = self.output_paths["danmaku_video"].replace(
            self.__anchor, self.__drive
        )

        video_res_x, video_res_y = self.get_resolution()
        filter_complex = f"""
            [1:v]scale={video_res_x}:{video_res_y}:force_original_aspect_ratio=decrease,pad={video_res_x}:{video_res_y}:-1:-1:color=black[v_fixed];
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
            [out]ass='{self.output_paths['ass']}'[out_sub]
        """
        filter_complex = filter_complex.replace("\n", "")

        # 使用 mp4 文件能显著提升压制速度（占满显卡）
        input_video = (
            f" -i \"{self.output_paths['early_video']}\""
            if early_video_exists
            else f"-f concat -safe 0 -i \"{self.output_paths['concat_file']}\""
        )
        output_video_options = (
            f" -preset p3 -cq 28"
            if RESULTS.no_limit
            else f" -preset slow"
            f" -b:v {video_bitrate}K -maxrate:v {max_video_bitrate}K -bufsize:v {video_bitrate * 2}K"
        )
        ffmpeg_command = (
            f"ffmpeg -y"
            f" -t {total_time}"
            f" -i \"{self.output_paths['he_graph']}\""
            f" {input_video}"
            f" -t {total_time}"
            f' -filter_complex "{filter_complex}" -map "[out_sub]" -map 1:a'
            f" -c:v h264_nvenc {output_video_options}"
            f" -profile:v high -rc vbr -rc-lookahead 32 -temporal-aq 1"
            f" -coder cabac -bf 3 -b_ref_mode middle -multipass fullres"
            f" -qmin 0 -g {int(avg_fps * gop)}"
            f" -c:a copy \"{self.output_paths['danmaku_video']}\""
            # f' >> "{self.output_paths["video_log"]}" 2>&1'
        )
        powershell_command = f"Measure-Command {{ {ffmpeg_command} | Out-Host }}"

        with open(self.output_paths["temp_ps1"], "w", encoding="gb18030") as f:
            f.write(powershell_command)

        self.output_paths["temp_ps1"] = self.output_paths["temp_ps1"].replace(
            self.__anchor, self.__drive
        )

        powershell_command = (
            f"PowerShell.exe"
            f" -File \"{self.output_paths['temp_ps1']}\""
            f" -ExecutionPolicy Bypass"
            f' >> "{self.output_paths["video_log"]}" 2>&1'
        )
        # print(powershell_command)
        # sp.run(powershell_command, shell=True, check=True)
        await async_wait_output(powershell_command)

    async def gen_preparation(self):
        await self.process_xml()
        await self.process_danmaku()
        await self.process_thumbnail()
        self.generate_concat()

    async def gen_early_video(self):
        await self.process_early_video()

    async def gen_danmaku_video(self):
        await self.process_video()
        if self.__upload:
            danmaku_video = self.output_paths["danmaku_video"].replace(
                self.__drive, self.__anchor
            )
            upload_command = (
                f"aliyunpan upload"
                f' "{danmaku_video}"'
                f' "{(self.__drive_dir / self.__new_dirname.name).as_posix()}"'
                f' >> "{self.output_paths["extras_log"]}" 2>&1'
            )
            await async_wait_output(upload_command)

    async def upload_aDrive(self):
        self.__upload = True
        early_video = pathlib.Path(self.output_paths["early_video"])
        old_dirname = early_video.parent.parent
        new_dirname = old_dirname.parent / f"{old_dirname.name} [Auto upload]"
        early_video.parent.rename(new_dirname)
        self.__new_dirname = new_dirname
        self.gen_output_paths(new_dirname)
        parent_dir = new_dirname.parent
        drive_dir = pathlib.PurePath("/", parent_dir.parent.name, parent_dir.name)
        self.__drive_dir = drive_dir
        escaped_mark = self.output_cache_mark.replace(".", "\\.")
        upload_command = (
            f"aliyunpan upload"
            f' -exn "{escaped_mark}.+$"'
            f' "{new_dirname.as_posix()}"'
            f' "{drive_dir.as_posix()}"'
            f' >> "{self.output_paths["extras_log"]}" 2>&1'
        )
        # aliyunpan 本身具有计时功能
        await async_wait_output(upload_command)


def gen_replay(dir_path: pathlib.Path, filenames: list[pathlib.Path]):
    print("Generating:", dir_path.as_posix())

    session = Session()
    for filename in filenames:
        video = Video(filename)
        asyncio.run(session.add_video(video))

    if len(session.videos) == 0:
        print(f'No video in "{dir_path}", skip!')
        exit()

    if not any(session.output_paths):
        session.gen_output_paths()

    if not RESULTS.no_preparation or RESULTS.all:
        asyncio.run(session.gen_preparation())

    if RESULTS.early_video or RESULTS.all:
        asyncio.run(session.gen_early_video())
    if RESULTS.upload:
        asyncio.run(session.upload_aDrive())
    if RESULTS.danmaku_video or RESULTS.all:
        asyncio.run(session.gen_danmaku_video())


def watching_dir(
    active_dir: pathlib.Path, old_file_num: int, old_dir_size: int, active_dir_size: int
):
    print("Watching:", active_dir.as_posix())
    while True:
        print(
            f"{time.ctime(time.time())}, old_dir_size: {old_dir_size}, dir_size: {active_dir_size}"
        )
        old_dir_size = active_dir_size
        time.sleep(90)
        active_files = list(active_dir.glob("*.flv"))
        active_dir_size = sum([file.stat().st_size for file in active_files])
        if old_dir_size == active_dir_size:
            active_file_num = len(active_files)
            all_files = list(active_dir.parent.rglob("*.flv"))
            if len(all_files) == old_file_num + active_file_num:
                gen_replay(active_dir, active_files)
                return
            else:
                # 修改了标题
                active_file = sorted(all_files, key=lambda f: f.stat().st_mtime)[-1]
                new_active_dir = active_file.parent
                if new_active_dir.name.split("-")[0] == active_dir.name.split("-")[0]:
                    print(
                        "Rename Title from",
                        active_dir.name.split("-")[-1],
                        "to",
                        new_active_dir.name.split("-")[-1],
                    )
                    for child in active_dir.iterdir():
                        print("rename", child.name)
                        child.rename(new_active_dir / child.name)
                    active_dir.rmdir()
                    active_dir = new_active_dir
                else:
                    gen_replay(active_dir, active_files)
                    watching_dir(
                        new_active_dir,
                        old_file_num + active_file_num,
                        0,
                        active_file.stat().st_size,
                    )
                    return


def waiting_dir(dir_path: pathlib.Path, old_file_num: int, old_dir_size: int):
    print("Monitoring:", dir_path.as_posix())
    while True:
        filenames = list(dir_path.rglob("*.flv"))
        file_num = len(filenames)
        dir_size = sum([filename.stat().st_size for filename in filenames])
        print(f"{time.ctime(time.time())}, file_num: {file_num}, dir_size: {dir_size}")
        if file_num <= old_file_num and dir_size <= old_dir_size:
            old_file_num = file_num
            old_dir_size = dir_size
            time.sleep(600)
        else:
            active_file = sorted(filenames, key=lambda f: f.stat().st_mtime)[-1]
            active_dir = active_file.parent
            active_files = list(active_dir.glob("*.flv"))
            active_file_num = len(active_files)
            active_dir_size = sum([file.stat().st_size for file in active_files])
            watching_dir(active_dir, file_num - active_file_num, 0, active_dir_size)
            return


def main(dir_path: pathlib.Path):
    print(f"{dir_path.as_posix()}:")
    if RESULTS.no_watch:
        gen_replay(dir_path, list(dir_path.glob("*.flv")))
    else:
        while True:
            # Generator will lost after being used. So we use list() to expand.
            filenames = list(dir_path.rglob("*.flv"))
            old_file_num = len(filenames)
            old_dir_size = sum([filename.stat().st_size for filename in filenames])
            print(
                f"{time.ctime(time.time())}, old_file_num: {old_file_num}, old_dir_size: {old_dir_size}"
            )
            time.sleep(90)
            waiting_dir(dir_path, old_file_num, old_dir_size)


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(
        description="Generate danmaku videos from bilibili recorder.",
        epilog=r"e.g.: $python %(prog)s dir_path",
        allow_abbrev=False,
    )
    PARSER.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s version 1.0 author:@lengyanyu258",
    )
    PARSER.add_argument(
        "dir_path",
        help="flv videos generated by BililiveRecorder directory path.",
    )
    PARSER.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Generate all.",
    )
    PARSER.add_argument(
        "-u",
        "--upload",
        action="store_true",
        help="Upload generated files.",
    )
    PARSER.add_argument(
        "-nl",
        "--no_limit",
        action="store_true",
        help="Do not limit video rate.",
    )
    PARSER.add_argument(
        "-nw",
        "--no_watch",
        action="store_true",
        help="Do not Watching folder.",
    )
    PARSER.add_argument(
        "-np",
        "--no_preparation",
        action="store_true",
        help="Do not generate preparation.",
    )
    PARSER.add_argument(
        "-ev",
        "--early_video",
        action="store_true",
        help="Generate early video.",
    )
    PARSER.add_argument(
        "-dv",
        "--danmaku_video",
        action="store_true",
        help="Generate danmaku video.",
    )

    RESULTS = PARSER.parse_args()
    DIR_PATH = RESULTS.dir_path

    # strip ambiguous chars.
    DIR_PATH = DIR_PATH.encode().translate(None, delete='*?"<>|'.encode()).decode()

    if (DIR_PATH := pathlib.Path(DIR_PATH)).is_dir():
        main(DIR_PATH)
    else:
        print(RESULTS.dir_path)
        print(DIR_PATH, "Dir Not Exist!")
