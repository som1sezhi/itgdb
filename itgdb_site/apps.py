import os
from django.apps import AppConfig
from django.conf import settings


class ItgdbSiteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'itgdb_site'

    def ready(self):
        # implicitly connects signal handlers decorated with @receiver
        from . import signals

        # ensure packs/ and extracted/ dirs exist in MEDIA_ROOT
        for dir_name in ('packs', 'extracted'):
            path = str(settings.MEDIA_ROOT / dir_name)
            if not os.path.exists(path):
                os.mkdir(path)