from django.core.files.storage import storages
from django.db import models
from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.indexes import GinIndex

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
        splits = self.image.name.split("_", 1)
        name = splits[1 if len(splits) > 1 else 0]
        return f'{self.id}: {name}'


class Tag(models.Model):
    name = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name


class PackCategory(models.Model):
    name = models.CharField(max_length=32, unique=True)
    abbr = models.CharField(max_length=4, blank=True, null=True)
    color = models.CharField(max_length=32, blank=True, null=True)

    def __str__(self):
        return self.name


class Pack(models.Model):
    name = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=255, blank=True)
    release_date = models.DateTimeField(blank=True, null=True)
    upload_date = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    category = models.ForeignKey(
        PackCategory, on_delete=models.SET_NULL, blank=True, null=True
    )
    tags = models.ManyToManyField(Tag, blank=True)
    links = models.TextField(blank=True)
    banner = models.ForeignKey(
        ImageFile, on_delete=models.SET_NULL, related_name='banner_packs',
        blank=True, null=True
    )

    def __str__(self):
        return self.name


class Song(models.Model):
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=500, blank=True)
    subtitle = models.CharField(max_length=500, blank=True)
    artist = models.CharField(max_length=255, blank=True)
    title_translit = models.CharField(max_length=500, blank=True)
    subtitle_translit = models.CharField(max_length=500, blank=True)
    artist_translit = models.CharField(max_length=255, blank=True)
    credit = models.CharField(max_length=255, blank=True)
    min_bpm = models.FloatField()
    max_bpm = models.FloatField()
    min_display_bpm = models.FloatField(null=True, blank=True)
    max_display_bpm = models.FloatField(null=True, blank=True)
    length = models.FloatField()
    release_date = models.DateTimeField(null=True, blank=True)
    upload_date = models.DateTimeField(null=True, blank=True, auto_now_add=True)
    links = models.TextField(blank=True, default='')
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
    has_bgchanges = models.BooleanField(default=False)
    has_fgchanges = models.BooleanField(default=False)
    has_attacks = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(pack__isnull=True) | models.Q(links__exact=''),
                name='links_only_for_singles'
            )
        ]

    def __str__(self):
        if self.pack:
            return f'[{self.pack.name}] {self.title} {self.subtitle}'
        return f'[<single>] {self.title} {self.subtitle}'
    
    def get_charts_by_difficulty(self):
        charts = [
            [None, None, None, None, None, []]
            for _ in range(2)
        ]
        for chart in self.chart_set.all():
            type_idx = chart.steps_type - 1
            diff = chart.difficulty
            if diff == 5: # edit diff
                charts[type_idx][diff].append(chart)
            else:
                charts[type_idx][diff] = chart
        return charts


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
    )

    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    steps_type = models.SmallIntegerField(choices=STEPS_TYPE_CHOICES)
    difficulty = models.SmallIntegerField(choices=DIFFICULTY_CHOICES)
    meter = models.IntegerField()
    credit = models.CharField(max_length=255, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    chart_name = models.CharField(max_length=255, blank=True, default='')
    chart_hash = models.CharField(max_length=40)
    release_date = models.DateTimeField(null=True, blank=True)
    upload_date = models.DateTimeField(null=True, blank=True, auto_now_add=True)
    density_graph = models.JSONField()
    has_attacks = models.BooleanField(default=False)
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

    class Meta:
        indexes = [
            models.Index(fields=['steps_type']),
            models.Index(fields=['difficulty']),
            models.Index(fields=['meter']),
        ]

    @staticmethod
    def steps_type_to_int(steps_type: str):
        return Chart.STEPS_TYPE_MAPPING.get(steps_type)

    @staticmethod
    def difficulty_str_to_int(diff: str):
        diff = diff.lower()
        return Chart.DIFFICULTY_MAPPING.get(diff)
    
    def __str__(self):
        return '[%s] %s %s (%s %s)' % (
            self.song.pack.name if self.song.pack else '<single>',
            self.song.title,
            self.song.subtitle,
            Chart.STEPS_TYPE_CHOICES[self.steps_type],
            Chart.DIFFICULTY_CHOICES[self.difficulty]
        )
    
    def get_chart_info(self):
        lines = [
            ('credit', self.credit),
            ('description', self.description),
            ('chartname', self.chart_name),
        ]
        lines_to_fields = {}
        for k, line in lines:
            if line:
                if line in lines_to_fields:
                    lines_to_fields[line] += (k,)
                else:
                    lines_to_fields[line] = (k,)
        return {v: k for k, v in lines_to_fields.items()}
