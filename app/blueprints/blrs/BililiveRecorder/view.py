from apiflask import APIBlueprint

from ..utils import get_input_examples
from .schema import BililiveRecorder, BililiveRecorderEvents

bililive_recorder_name = __package__.rsplit(".", 1)[-1]

bp = APIBlueprint(bililive_recorder_name, __name__)


@bp.post(f"/{bililive_recorder_name}")
@bp.input(
    BililiveRecorder,
    examples=get_input_examples(__file__, "type", BililiveRecorderEvents),
)
@bp.output({}, status_code=204)
@bp.doc(description="将该地址添加到对应录播程序设置中的 Webhook 中")
def webhook_url(json_data):
    print(json_data)
    event = json_data["type"]
    return ""
