from django.core.files.storage import storages
from django.db import models

# Callables to pass into the storage argument of a FileField/ImageField.
# Using a callable prevents the storage from being hardcoded into
# database migrations.
def get_simfiles_storage():
    return storages['simfiles']

def get_simfilemedia_storage():
    return storages['simfilemedia']


class ImageFile(models.Model):
    pack = models.ForeignKey('Pack', on_delete=models.CASCADE, blank=True, null=True)
    image = models.ImageField(storage=get_simfilemedia_storage)

    def __str__(self):
        return f'[{self.pack.name}] {self.image.name.split("_", 1)[1]}'


class Tag(models.Model):
    name = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name


class Pack(models.Model):
    name = models.CharField(max_length=255, blank=True)
    release_date = models.DateTimeField()
    tags = models.ManyToManyField(Tag, blank=True)
    banner = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='banner_packs',
        blank=True, null=True
    )

    def __str__(self):
        return self.name


class Song(models.Model):
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, null=True)
    title = models.CharField(max_length=500)
    subtitle = models.CharField(max_length=500)
    artist = models.CharField(max_length=255)
    title_translit = models.CharField(max_length=500)
    subtitle_translit = models.CharField(max_length=500)
    artist_translit = models.CharField(max_length=255)
    credit = models.CharField(max_length=255)
    min_bpm = models.FloatField()
    max_bpm = models.FloatField()
    min_display_bpm = models.FloatField(null=True, blank=True)
    max_display_bpm = models.FloatField(null=True, blank=True)
    length = models.FloatField()
    release_date = models.DateTimeField()
    simfile = models.FileField(storage=get_simfiles_storage)
    banner = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='banner_songs',
        blank=True, null=True
    )
    bg = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='bg_songs',
        blank=True, null=True
    )
    cdtitle = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='cdtitle_songs',
        blank=True, null=True
    )
    jacket = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='jacket_songs',
        blank=True, null=True
    )

    def __str__(self):
        return f'[{self.pack.name}] {self.title} {self.subtitle}'


class Chart(models.Model):
    STEPS_TYPE_CHOICES = {
        1: 'dance-single',
        2: 'dance-double'
    }
    DIFFICULTY_CHOICES = {
        0: 'beginner',
        1: 'easy',
        2: 'medium',
        3: 'hard',
        4: 'challenge',
        5: 'edit'
    }
    STEPS_TYPE_MAPPING = {v: k for k, v in STEPS_TYPE_CHOICES.items()}
    DIFFICULTY_MAPPING = dict(
        **{v: k for k, v in DIFFICULTY_CHOICES.items()},
        expert=4
    )

    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    steps_type = models.SmallIntegerField(choices=STEPS_TYPE_CHOICES)
    difficulty = models.SmallIntegerField(choices=DIFFICULTY_CHOICES)
    meter = models.IntegerField()
    credit = models.CharField(max_length=255, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    chart_name = models.CharField(max_length=255, null=True, blank=True)
    chart_hash = models.CharField(max_length=40)
    objects_count = models.PositiveIntegerField()
    steps_count = models.PositiveIntegerField()
    combo_count = models.PositiveIntegerField()
    jumps_count = models.PositiveIntegerField()
    mines_count = models.PositiveIntegerField()
    hands_count = models.PositiveIntegerField()
    holds_count = models.PositiveIntegerField()
    rolls_count = models.PositiveIntegerField()
    lifts_count = models.PositiveIntegerField()
    fakes_count = models.PositiveIntegerField()

    @staticmethod
    def steps_type_to_int(steps_type: str):
        return Chart.STEPS_TYPE_MAPPING[steps_type]

    @staticmethod
    def difficulty_str_to_int(diff: str):
        diff = diff.lower()
        return Chart.DIFFICULTY_MAPPING[diff]
    
    def __str__(self):
        return '[%s] %s %s (%s %s)' % (
            self.song.pack.name,
            self.song.title,
            self.song.subtitle,
            Chart.STEPS_TYPE_CHOICES[self.steps_type],
            Chart.DIFFICULTY_CHOICES[self.difficulty]
        )
