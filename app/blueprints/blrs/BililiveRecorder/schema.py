from enum import StrEnum

from apiflask import Schema
from apiflask.fields import UUID, AwareDateTime, Dict, Enum, String


class BililiveRecorderEvents(StrEnum):
    """https://github.com/acgnhiki/blrec/blob/master/src/blrec/event/typing.py#L42-L60

    permalink: https://github.com/acgnhiki/blrec/blob/8dc32e5e6ef80ec67a50e45b9d260c7403c4bb9f/src/blrec/event/typing.py#L42-L60
    """

    LiveBeganEvent = "开播"
    LiveEndedEvent = "下播"
    RoomChangeEvent = "直播间信息改变"
    RecordingStartedEvent = "录制开始"
    RecordingFinishedEvent = "录制完成"
    RecordingCancelledEvent = "录制取消"
    VideoFileCreatedEvent = "视频文件创建"
    VideoFileCompletedEvent = "视频文件完成"
    DanmakuFileCreatedEvent = "弹幕文件创建"
    DanmakuFileCompletedEvent = "弹幕文件完成"
    RawDanmakuFileCreatedEvent = "原始弹幕文件创建"
    RawDanmakuFileCompletedEvent = "原始弹幕文件完成"
    CoverImageDownloadedEvent = "直播封面下载完成"
    VideoPostprocessingCompletedEvent = "视频后处理完成"
    PostprocessingCompletedEvent = "文件后处理完成"
    SpaceNoEnoughEvent = "硬盘空间不足"
    Error = "程序出现异常"


class BililiveRecorder(Schema):
    id = UUID()
    date = AwareDateTime()
    type = Enum(BililiveRecorderEvents, required=True)
    data = Dict(keys=String, required=True)
