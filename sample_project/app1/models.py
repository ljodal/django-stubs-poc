from django.db import models


class ModelA(models.Model):
    model_b = models.ForeignKey(
        "app2.ModelB", related_name="a_s", on_delete=models.CASCADE, null=True
    )

    def test(self) -> int | None:
        return self.model_b_id
