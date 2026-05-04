from django.contrib import admin

from .models import LcPage


@admin.register(LcPage)
class LcPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "size_bytes", "updated_at")
    search_fields = ("title", "slug")
    readonly_fields = ("id", "html_path", "events_path", "size_bytes", "created_at", "updated_at")
