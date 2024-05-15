from apiflask import APIBlueprint

blrs = APIBlueprint(
    "blrs",
    __name__,
    tag="Bililive Recorders",
    enable_openapi=False,
    url_prefix="/blrs",
)

from . import blrec

blrs.register_blueprint(blrec.bp)
