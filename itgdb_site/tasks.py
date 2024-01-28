import mimetypes
import os
import shutil
import uuid
import zipfile
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from simfile.dir import SimfilePack
from simfile.timing.displaybpm import displaybpm
import mutagen
from celery import shared_task
import cv2

from .models import Pack, Song, Chart, ImageFile
from .utils.charts import get_hash, get_counts


def get_image(path, pack, cache):
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
        image_cache = {}
        with transaction.atomic():
            simfile_pack = SimfilePack(pack_path)
            p = Pack(
                name = pack_data['name'] or simfile_pack.name,
                release_date = pack_data['release_date']
            )
            p.save()
            p.tags.add(*pack_data['tags'])
            p.banner = get_image(simfile_pack.banner(), p, image_cache)
            p.save()

            for simfile_dir in simfile_pack.simfile_dirs():
                sim = simfile_dir.open()
                assets = simfile_dir.assets()
                sim_path = simfile_dir.simfile_path
                sim_filename = os.path.basename(sim_path)

                music_path = assets.music
                audio = mutagen.File(music_path)

                bpm = displaybpm(sim, ignore_specified=True)
                disp = displaybpm(sim)
                bpm_range = (bpm.min, bpm.max)
                disp_range = (disp.min, disp.max)

                f = open(sim_path, 'rb')
                sim_uuid = uuid.uuid4()

                s = p.song_set.create(
                    title = sim.title,
                    subtitle = sim.subtitle,
                    artist = sim.artist,
                    title_translit = sim.titletranslit,
                    subtitle_translit = sim.subtitletranslit,
                    artist_translit = sim.artisttranslit,
                    credit = sim.credit,
                    min_bpm = bpm_range[0],
                    max_bpm = bpm_range[1],
                    min_display_bpm = disp_range[0],
                    max_display_bpm = disp_range[1],
                    length = audio.info.length,
                    release_date = p.release_date,
                    simfile = File(f, name=f'{sim_uuid}_{sim_filename}'),
                    banner = get_image(assets.banner, p, image_cache),
                    bg = get_image(assets.background, p, image_cache),
                    cdtitle = get_image(assets.cdtitle, p, image_cache),
                    jacket = get_image(assets.jacket, p, image_cache),
                )
                f.close()

                for chart in sim.charts:
                    chart_hash = get_hash(sim, chart)
                    counts = get_counts(sim, chart)
                    counts = {k + '_count': v for k, v in counts.items()}
                    s.chart_set.create(
                        steps_type = Chart.steps_type_to_int(chart.stepstype),
                        difficulty = Chart.difficulty_str_to_int(chart.difficulty),
                        meter = int(chart.meter),
                        credit = chart.get('CREDIT'),
                        description = chart.description,
                        chart_name = chart.get('CHARTNAME'),
                        chart_hash = chart_hash,
                        **counts
                    )
    finally:
        shutil.rmtree(extract_path)