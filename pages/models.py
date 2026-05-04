import uuid

from django.db import models


class LcPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=120)
    title = models.CharField(max_length=200)
    # Storage keys (relative to MEDIA_ROOT or the configured S3 bucket).
    html_path = models.CharField(max_length=500)
    events_path = models.CharField(max_length=500)
    size_bytes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.slug})"
