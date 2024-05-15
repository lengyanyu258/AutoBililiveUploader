import os
import shutil
import tomllib

from apiflask import APIFlask


def create_app():
    app = APIFlask(__name__)

    app.config.from_pyfile("config.py")
    app.title = app.config["TITLE"]
    app.version = app.config["VERSION"]

    while not app.config.from_file(
        os.path.join(app.instance_path, "config.toml"),
        load=tomllib.load,
        silent=True,
        text=False,
    ):
        # ensure the instance folder exists
        os.makedirs(app.instance_path, exist_ok=True)
        shutil.copy(os.path.join(app.root_path, "config.toml"), app.instance_path)

    from .blueprints.blrs import blrs as blrs_blueprint
    from .blueprints.main import main as main_blueprint

    app.register_blueprint(blrs_blueprint)
    app.register_blueprint(main_blueprint)

    return app
