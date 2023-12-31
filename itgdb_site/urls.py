from django.urls import path

from . import views
from .admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('', views.index, name='index'),
]