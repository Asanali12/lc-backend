from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from pages.views import presets_collection


def health(_request):
    return JsonResponse({"ok": True, "service": "lc-backend"})


urlpatterns = [
    path("", health),
    path("admin/", admin.site.urls),
    path("api/lc-pages/", include("pages.urls")),
    # Global event-preset library — not page-scoped, lives at the top level.
    path("api/lc-presets/", presets_collection, name="lc-presets"),
]
