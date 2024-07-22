import mimetypes
import os
import shutil
import uuid
import zipfile
import csv
import time
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from simfile.dir import SimfilePack
from simfile.timing.displaybpm import displaybpm
from celery import shared_task
from celery.utils.log import get_task_logger
import cv2
from sorl.thumbnail import get_thumbnail
from celery_progress.backend import ProgressRecorder

from .models import Pack, Song, Chart, ImageFile
from .utils.charts import (
    get_hash, get_counts, get_density_graph, get_assets, get_pack_banner_path,
    get_song_lengths
)
from .utils.uploads import upload_pack

logger = get_task_logger(__name__)


def get_image(path, pack, cache, generate_thumbnail=False):
    if not path or not os.path.isfile(path):
        return None
    if path in cache:
        return cache[path]
    
    mimetype = mimetypes.guess_type(path)[0]
    img_path = None
    if mimetype.startswith('image'):
        img_path = path 
    elif mimetype.startswith('video'):
        # get first frame of video
        video_capture = cv2.VideoCapture(path)
        success, img = video_capture.read()
        if success:
            img_path = path + '.png'
            cv2.imwrite(img_path, img)
        video_capture.release()

    if img_path:
        with open(img_path, 'rb') as f:
            base_filename = os.path.basename(img_path)
            img_file = ImageFile(
                pack = pack,
                image = File(f, name=f'{uuid.uuid4()}_{base_filename}')
            )
            img_file.save()
            if generate_thumbnail:
                # pregenerate thumbnail
                # NOTE: geometry string here is for banner thumbnails
                get_thumbnail(img_file.image, 'x50')
            cache[path] = img_file
            return img_file
    
    return None


@shared_task()
def process_pack_upload(pack_data, filename):
    # TODO: error handling

    file = default_storage.open(filename)
    extract_dir = os.path.basename(filename).rsplit('.')[0]
    extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', extract_dir)
    # TODO: support for other archive types, maybe
    # TODO: likely susceptible to malicious zips (zip bombs, etc.)
    with zipfile.ZipFile(file) as z:
        z.extractall(extract_path)
    default_storage.delete(filename)

    try:
        # TODO: we assume that the zip contains only a pack directory, with all
        # the song folders inside. is this a good assumption?
        pack_name = next(os.walk(extract_path))[1][0]
        pack_path = os.path.join(extract_path, pack_name)
        # TODO: handle uploaded image/sim files better on rollback
        # https://github.com/un1t/django-cleanup/issues/43
        with transaction.atomic():
            simfile_pack = SimfilePack(pack_path)
            upload_pack(simfile_pack, pack_data)
    finally:
        shutil.rmtree(extract_path)


@shared_task()
def process_batch_upload(filename):
    f = default_storage.open(filename, 'r')
    with f.open('r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            print(row)
    default_storage.delete(filename)
    upload_pack()


@shared_task(bind=True)
def test_task(self, sleep_time):
    progress_recorder = ProgressRecorder(self)
    for i in range(sleep_time):
        time.sleep(1)
        progress_recorder.set_progress(i + 1, sleep_time, description=f'sleeping for {i+1} seconds')
    return sleep_time + 1