"""
Test mypy plugin
"""
from functools import partial
from typing import Callable

from mypy.nodes import (AssignmentStmt, CallExpr, Import, ImportAll,
                        ImportFrom, MemberExpr, MypyFile, NameExpr,
                        PlaceholderNode, StrExpr, TypeInfo)
from mypy.options import Options
from mypy.plugin import ClassDefContext, Plugin
from mypy.server.trigger import make_wildcard_trigger
from mypy.types import Instance

from . import helpers
from .context import DjangoContext

FOREIGN_KEY_FULLNAME = "django.db.models.fields.related.ForeignKey"
SETTINGS_FULLNAME = "django.conf"
CONTRIB_PACKAGES_WITH_MODELS = frozenset(
    {
        "django.contrib.auth"
        "django.contrib.admin"
        "django.contrib.flatpages"
        "django.contrib.sites"
        "django.contrib.redirects"
        "django.contrib.sessions"
        "django.contrib.contenttypes"
    }
)


class DjangoPlugin(Plugin):
    def __init__(self, options: Options) -> None:
        super().__init__(options)

        self.context = DjangoContext("sample_project.settings")

    def get_base_class_hook(
        self, fullname: str
    ) -> Callable[[ClassDefContext], None] | None:
        """
        Callback when a subclass is defined. We use this to extract field
        details and other context needed about models and views.
        """

        if fullname == "django.db.models.base.Model":
            return partial(ModelTransformer, django_context=self.context)

        return None

    def get_additional_deps(self, file: MypyFile) -> list[tuple[int, str, int]]:
        """
        Declare extra dependencies to simulate the Django runtime behavior where
        modules are automatically loaded based on the INSTALLED_APPS settings.
        """

        # print(f"get_additional_deps({file.fullname})")

        # Tell mypy that django.conf depends on the settings module, as that's
        # where the settings are acutally defined. The django.config.settings
        # object is mostly a lazy wrapper around the actual settings module.
        if file.fullname == SETTINGS_FULLNAME:
            return [(10, self.context.settings_module, -1)]

        # The settings module depends on all the modules in the INSTALLED_APPS
        # setting. This way we can ensure that all models are loaded
        if file.fullname == self.context.settings_module:
            self.context.installed_apps = helpers.get_installed_apps(file)
            installed_apps = self.context.installed_apps.copy()
            # For contrib apps we add model dependencies immediately, as we
            # know which ones contain concrete models
            installed_apps += (
                f"{app}.models"
                for app in installed_apps
                if app in CONTRIB_PACKAGES_WITH_MODELS
            )
            # NOTE: Handle installed apps linking to an explicit AppConfig
            # It is possible to define installed apps as my.app.MyAppConfig,
            # which would point to an attribute rather than a python module.
            # These need to be handled somehow, as I assume it'll otherwise
            # cause errors during the mypy checking
            return [(10, app, -1) for app in self.context.installed_apps]

        # Models are implicitly loaded by Django during setup, so there might
        # not be a explicitly imported even though they are used. We need all
        # modules to be loaded so we can resolve relationships between models.
        #
        # Ideally we'd only check modules in the INSTALLED_APPS setting, but
        # when we resolve that setting we don't know _where_ the modules are
        # defined and don't have access to mypy's search path. The best we can
        # do is exclude modules once we've seen INSTALLED_APPS .
        if file.is_package_init_file() and self.context.could_be_app(file.fullname):
            defs = []
            if helpers.has_submodule(file, "models"):
                defs.append((10, f"{file.fullname}.models", -1))
            if helpers.has_submodule(file, "apps"):
                defs.append((10, f"{file.fullname}.apps", -1))

            if defs:
                return defs

        # TODO: Look for apps.py files with AppConfig classes

        return []


class ModelTransformer:
    def __init__(self, ctx: ClassDefContext, django_context: DjangoContext) -> None:
        self.ctx = ctx
        self.django_context = django_context

        if ctx.cls.info.name not in ("ModelA", "ModelB"):
            return

        self.collect_foreign_keys()

    def collect_foreign_keys(self) -> None:
        cls = self.ctx.cls

        for stmt in cls.defs.body:
            if not (
                isinstance(stmt, AssignmentStmt)
                # Check that we assign to a single name
                and len(stmt.lvalues) == 1
                and isinstance(stmt.lvalues[0], NameExpr)
                # Check that the assigned value is a call to ForeignKey
                and isinstance(stmt.rvalue, CallExpr)
                and isinstance(stmt.rvalue.callee, MemberExpr | NameExpr)
                # TODO: Replace with check for superclass
                and stmt.rvalue.callee.fullname == FOREIGN_KEY_FULLNAME
            ):
                # print(f"Skipping statement: {stmt}")
                continue

            name = stmt.lvalues[0].fullname
            expr = stmt.rvalue

            if to_expr := helpers.get_argument(
                expr, name="to", pos=0, typ=StrExpr  # TODO: StrExpr | NameExpr
            ):
                to = to_expr.value
            else:
                continue

            if "." in to:
                app_label, to = to.split(".", 1)
                to_module = self.django_context.get_module(app_label)
                if to_module is None:
                    if not self.ctx.api.final_iteration:
                        return self.ctx.api.defer()
                    else:
                        raise RuntimeError(f"Unable to locate app: {app_label=}")
            else:
                to_module = cls.fullname

            to_fullname = f"{to_module}.models.{to}"

            if related_name_expr := helpers.get_argument(
                expr, name="related_name", pos=2, typ=StrExpr
            ):
                related_name = related_name_expr.value
            else:
                related_name = None  # TODO: Set default related name

            if null_expr := helpers.get_argument(expr, name="null", typ=NameExpr):
                null = null_expr.fullname == "builtins.True"
            else:
                null = False

            if (
                sym := self.ctx.api.lookup_fully_qualified_or_none(to_fullname)
            ) and isinstance(sym.node, TypeInfo):
                print(f"{to_fullname} is defined: {sym=}")
            elif (
                sym is None or isinstance(sym.node, PlaceholderNode)
            ) and not self.ctx.api.final_iteration:
                print(f"{to_fullname} is not defined or a placeholder, deferring")
                return self.ctx.api.defer()
            else:
                raise RuntimeError(f"Unable to find model: {to_fullname}")

            # If this model changes the referenced model needs to be updated as well
            self.ctx.api.add_plugin_dependency(
                make_wildcard_trigger(cls.fullname), target=to_fullname
            )

            if related_name:
                manager = self.ctx.api.lookup_fully_qualified(
                    "django.db.models.manager.Manager"
                )
                assert isinstance(manager.node, TypeInfo)
                helpers.add_new_sym_for_info(
                    sym.node,
                    name=related_name,
                    sym_type=Instance(manager.node, [Instance(cls.info, [])]),
                )
