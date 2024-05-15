from apiflask import APIBlueprint

from ..utils import get_input_examples
from .schema import BlrecEvents, BlrecInput
from .schema import type_field_name as type_field

bililive_recorder_name = __package__.rsplit(".", maxsplit=1)[-1]

bp = APIBlueprint(
    bililive_recorder_name,
    __name__,
    tag={
        "name": bililive_recorder_name,
        "description": "Bilibili Live Streaming Recorder 哔哩哔哩直播录制 \u2013 [Github](https://github.com/acgnhiki/blrec)",
    },
    url_prefix=f"/{bililive_recorder_name}",
)


@bp.post("/webhook")
@bp.input(
    BlrecInput,
    examples=get_input_examples(
        bp.open_resource("examples.json"), type_field, BlrecEvents
    ),
)
@bp.output({}, status_code=204)
@bp.doc(description="将该地址添加到对应录播程序设置中的 Webhook 中")
def webhook_url(json_data):
    print(json_data)
    event = json_data[type_field]
    return ""
