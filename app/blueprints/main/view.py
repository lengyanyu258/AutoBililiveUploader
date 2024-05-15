import functools

from flask import flash, g, redirect, render_template, request, session, url_for
from jinja2 import TemplateNotFound

from . import main


@main.get("/")
def index():
    """Say hello

    Some description for the /hello
    """
    return redirect("docs")
