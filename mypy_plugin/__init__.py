from mypy.plugin import Plugin

from .plugin import DjangoPlugin


def plugin(version: str) -> type[Plugin]:
    """
    `version` is the mypy version string
    We might want to use this to print a warning if the mypy version being used is
    newer, or especially older, than we expect (or need).
    """

    return DjangoPlugin
