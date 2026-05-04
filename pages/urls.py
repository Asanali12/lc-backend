from django.urls import path

from . import views

urlpatterns = [
    path("", views.collection, name="lc-page-collection"),
    path("<str:id_or_slug>/", views.detail, name="lc-page-detail"),
    path("<str:id_or_slug>/html", views.raw_html, name="lc-page-html"),
    path("<str:id_or_slug>/events", views.raw_events, name="lc-page-events"),
]
