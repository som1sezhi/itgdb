from django.dispatch import receiver
from django_cleanup.signals import cleanup_pre_delete
from sorl.thumbnail import delete


@receiver(cleanup_pre_delete)
def sorl_delete_thumbnails(**kwargs):
    delete(kwargs['file'])