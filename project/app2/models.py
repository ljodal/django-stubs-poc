from django.db import models


class ModelB(models.Model):
    model_a = models.ForeignKey(
        "app1.ModelA", related_name="b_s", on_delete=models.CASCADE
    )
