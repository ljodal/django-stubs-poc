from functools import cache
from pathlib import Path
from typing import TypeVar

from mypy.nodes import (MDEF, AssignmentStmt, CallExpr, ListExpr, MypyFile,
                        NameExpr, StrExpr, SymbolTableNode, TypeInfo, Var)
from mypy.types import Type as MypyType

T = TypeVar("T")


def get_argument(
    expr: CallExpr, *, name: str | None = None, pos: int | None = None, typ: type[T]
) -> T | None:
    # Check for positional arguments first
    if (
        pos is not None
        and len(expr.arg_names) >= pos
        and expr.arg_names[pos] is None
        and isinstance(expr.args[pos], typ)
    ):
        # We've done an instance check here, but mypy doesn't understand that
        return expr.args[pos]  # type: ignore[return-value]

    # Then try keyword args
    if name is not None:
        try:
            idx = expr.arg_names.index(name)
        except ValueError:
            return None

        if isinstance(expr.args[idx], typ):
            # We've done an instance check here, but mypy doesn't understand that
            return expr.args[idx]  # type: ignore[return-value]

    return None


def get_installed_apps(file: MypyFile) -> list[str]:
    for stmt in file.defs:
        if not (
            isinstance(stmt, AssignmentStmt)
            and len(stmt.lvalues) == 1
            and isinstance(stmt.lvalues[0], NameExpr)
            and stmt.lvalues[0].name == "INSTALLED_APPS"
        ):
            continue

        if isinstance(stmt.rvalue, ListExpr):
            return [
                item.value for item in stmt.rvalue.items if isinstance(item, StrExpr)
            ]

    return []


def has_submodule(file: MypyFile, name: str) -> bool:
    return file.is_package_init_file() and _has_submodule(Path(file.path).parent, name)


@cache  # TODO: Ensure this caching is safe wrt dmypy
def _has_submodule(path: Path, name: str) -> bool:
    return (path / f"{name}.py").exists() or (path / name / "__init__.py").exists()


def add_new_sym_for_info(
    info: TypeInfo, *, name: str, sym_type: MypyType, no_serialize: bool = False
) -> None:
    # type=: type of the variable itself
    var = Var(name=name, type=sym_type)
    # var.info: type of the object variable is bound to
    var.info = info
    var._fullname = info.fullname + "." + name
    var.is_initialized_in_class = True
    var.is_inferred = True
    info.names[name] = SymbolTableNode(
        MDEF, var, plugin_generated=True, no_serialize=no_serialize
    )
