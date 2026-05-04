from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"ok": True, "service": "lc-backend"})


urlpatterns = [
    path("", health),
    path("admin/", admin.site.urls),
    path("api/lc-pages/", include("pages.urls")),
]
