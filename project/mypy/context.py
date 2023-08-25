from mypy.nodes import MypyFile, TypeInfo

try:
    from sys import stdlib_module_names
except ImportError:
    # Only available in Python 3.10+
    stdlib_module_names = frozenset({"builtins"})

# Avoid looking for models files for packages we know do not contain models
KNOWN_NON_DJANGO_APPS = stdlib_module_names | {
    "_typeshed",
    "django",
    "django_stubs_ext",
    "mypy",
    "pkg_resources",
    "setuptools",
    "typing_extensions",
}


class DjangoContext:
    def __init__(self, settings_module: str) -> None:
        # Name of the django settings module
        self.settings_module: str = settings_module
        # List of installed apps, extracted from the settings module
        self.installed_apps: list[str] | None = None
        # Mapping from Django app label to python module name
        self._app_labels: dict[str, str] = {}
        # Mapping from (app_label, model_name) to model TypeInfo
        self.models: dict[tuple[str, str], TypeInfo] = {}

    def could_be_app(self, fullname: str) -> bool:
        top_level_name, *_ = fullname.split(".", 1)
        if top_level_name in KNOWN_NON_DJANGO_APPS:
            return False
        if self.installed_apps is not None:
            return fullname in self.installed_apps
        return True  # Before loading installed_apps we have no way of knowing

    def get_module(self, app_label: str) -> str | None:
        if module := self._app_labels.get(app_label):
            return module
        for app in self.installed_apps or ():
            if app.endswith(f".{app_label}"):
                return app
        return None

    def register_app(self, app_label: str, module: str) -> None:
        assert (
            self.installed_apps is not None
        ), "Cannot register apps before installed apps have been populated"
        if module in self.installed_apps:
            self._app_labels[app_label] = module

    def add_model(self, type_info: TypeInfo) -> None:
        module, model_name = type_info.fullname.rsplit(".", 1)
