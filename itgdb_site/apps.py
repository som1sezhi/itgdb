from django.apps import AppConfig


class ItgdbSiteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'itgdb_site'

    def ready(self):
        # implicitly connects signal handlers decorated with @receiver
        from . import signals