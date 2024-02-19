from django.conf import settings
from storages.backends.s3 import S3Storage


# since sorl-thumbnail's THUMBNAIL_STORAGE takes in a class path,
# we need to make a class for the thumbnail storage
class ThumbnailStorage(S3Storage):
    location = 'thumbs/'
    default_acl = 'public-read'