import tomllib
from pathlib import Path
from typing import Any, Dict, List

root_path = Path(__file__).parent
info: Dict[str, Any] = tomllib.loads(
    root_path.with_name("pyproject.toml").read_text(encoding="utf-8")
)["tool"]["poetry"]
readme = root_path.with_name("README.md").read_text(encoding="utf-8")
name: str = info["name"]
authors: List[str] = info["authors"]
license: str = info["license"]

# APP
TITLE = name.replace("-", " ").title()
VERSION: str = info["version"]

# OpenAPI
DESCRIPTION = readme.split("\n", maxsplit=1)[-1].strip()
TERMS_OF_SERVICE = info["urls"]["Terms of Service"]
CONTACT = {
    "name": "API Support",
    "url": info["urls"]["Bug Tracker"],
    "email": authors[0].rsplit(maxsplit=1)[-1].strip("<>"),
}
LICENSE: Dict[str, str] = {
    "name": license.replace("-", " "),
    "url": info["urls"]["LICENSE"],
}
EXTERNAL_DOCS = {
    "description": "Find more info here",
    "url": info["documentation"],
}

# Swagger UI
# https://cdnjs.com/libraries/swagger-ui
# https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui.min.css
SWAGGER_UI_CSS = "/static/css/swagger-ui.min.css"
# https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui-bundle.min.js
SWAGGER_UI_BUNDLE_JS = "/static/js/swagger-ui-bundle.min.js"
# https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.0/swagger-ui-standalone-preset.min.js
SWAGGER_UI_STANDALONE_PRESET_JS = "/static/js/swagger-ui-standalone-preset.min.js"
