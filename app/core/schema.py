from typing import Any, Dict

from marshmallow import Schema, fields, post_load


class Config:
    def __init__(self, version: str, tools: Dict[str, Dict[str, Any]]):
        self.version = version
        self.tools = tools
        self.created_at = dt.datetime.now()

    def __repr__(self):
        return "<Config(version={self.version!r})>".format(self=self)


class ConfigSchema(Schema):
    version = fields.Str()
    tools = fields.Dict()
    created_at = fields.DateTime()

    @post_load
    def make_user(self, data, **kwargs):
        return Config(**data)
