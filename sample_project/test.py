from .app1.models import ModelA
from .app2.models import ModelB


def test_something() -> None:
    a = ModelA()
    reveal_type(a.b_s)
    a.b_s.count()
