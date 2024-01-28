import os
import shutil
import zipfile
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
import simfile
from simfile.timing.displaybpm import displaybpm
import mutagen
from celery import shared_task

from .models import Pack, Song, Chart
from .utils.charts import get_hash, get_counts


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

    # TODO: we assume that the zip contains only a pack directory, with all
    # the song folders inside. is this a good assumption?
    pack_name = next(os.walk(extract_path))[1][0]
    pack_path = os.path.join(extract_path, pack_name)

    with transaction.atomic():
        p = Pack(
            name = pack_data['name'],
            release_date = pack_data['release_date']
        )
        p.save()
        p.tags.add(*pack_data['tags'])
        for sim, sim_path in simfile.openpack(pack_path):
            sim_dir, sim_filename = os.path.split(sim_path)
            sim_last_dir = os.path.basename(os.path.normpath(sim_dir))
            music_path = os.path.join(sim_dir, sim.music)
            audio = mutagen.File(music_path)
            bpm = displaybpm(sim, ignore_specified=True)
            disp = displaybpm(sim)
            bpm_range = (bpm.min, bpm.max)
            disp_range = (disp.min, disp.max)
            f = open(sim_path)
            storage_filename = f'{p.id}_{p.name}__{sim_last_dir}__{sim_filename}'
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
                simfile = File(f, name=storage_filename)
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

    shutil.rmtree(extract_path)