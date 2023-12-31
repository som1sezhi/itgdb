from django.apps import AppConfig


class ItgdbSiteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'itgdb_site'

from django.contrib.admin.apps import AdminConfig

class ItgdbSiteAdminConfig(AdminConfig):
    default_site = 'itgdb_site.admin.ItgdbAdminSite'
