from datetime import datetime, timezone, time
import csv
import logging
import json
import re
from django.contrib import admin
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.urls import re_path, path, reverse
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.html import format_html
from django.utils.timezone import make_aware, now
from django.contrib import messages
from admin_extra_buttons.api import ExtraButtonsMixin, button
from django_celery_results.admin import TaskResultAdmin, GroupResultAdmin
from django_celery_results.models import TaskResult, GroupResult
from celery import group
import celery.result

from .models import Tag, Pack, Song, Chart, ImageFile, PackCategory
from .forms import PackUploadForm, BatchUploadForm, UpdateAnalysesForm, ChangeReleaseDateForm, UploadPatchForm
from .tasks import process_pack_upload, process_pack_from_web, update_analyses, process_patch_upload

logger = logging.getLogger(__name__)


@admin.register(Pack)
class PackAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    search_fields = ['name']
    raw_id_fields = ['banner']
    list_display = ['name', 'pack_actions']
    readonly_fields = ['pack_actions']

    def get_urls(self):
        urls = super().get_urls()
        added_urls = [
            path(
                'change_pack_date/<int:pack_id>',
                self.admin_site.admin_view(self.change_pack_date),
                name='change_pack_date'
            ),
            path(
                'upload_patch/<int:pack_id>',
                self.admin_site.admin_view(self.upload_patch),
                name='upload_patch'
            ),
        ]
        return added_urls + urls
    
    def change_pack_date(self, req, pack_id):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = ChangeReleaseDateForm(req.POST)
            if form.is_valid():
                new_release_date = form.cleaned_data['new_release_date']
                with transaction.atomic():
                    pack = Pack.objects.get(pk=pack_id)
                    pack.release_date = new_release_date
                    pack.save()
                    Song.objects.filter(pack__id=pack_id).update(
                        release_date=new_release_date
                    )
                    Chart.objects.filter(song__pack__id=pack_id).update(
                        release_date=new_release_date
                    )
                messages.success(req,
                    f'Changed release date of {pack.name} to {new_release_date}.'
                )
                
                return HttpResponseRedirect(
                    reverse('admin:itgdb_site_pack_changelist')
                )
        else:
            form = ChangeReleaseDateForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/change_release_date.html', context)

    def upload_patch(self, req, pack_id):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = UploadPatchForm(req.POST, req.FILES)
            if form.is_valid():
                params = form.cleaned_data

                params['pack_id'] = pack_id
                
                # replace file with filename in data
                filename = None
                file = params['file']
                if file:
                    now = datetime.now().strftime('%Y%m%d%H%M%S')
                    path = 'packs/' + now + '_' + file.name
                    filename = default_storage.save(path, file)
                params['file'] = filename

                result = process_patch_upload.delay(params)
                
                return HttpResponseRedirect(
                    reverse('admin:task_progress_tracker', args=(result.id,))
                )
        else:
            form = UploadPatchForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/upload_patch.html', context)


    @admin.display
    def pack_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Set release date</a>'
            '<a class="button" href="{}">Upload patch</a>',
            reverse('admin:change_pack_date', args=(obj.id,)),
            reverse('admin:upload_patch', args=(obj.id,)),
        )

    @button()
    def pack_upload(self, req):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = PackUploadForm(req.POST, req.FILES)
            if form.is_valid():
                data = form.cleaned_data
                
                filename = None
                file = data['file']
                if file:
                    now = datetime.now().strftime('%Y%m%d%H%M%S')
                    path = 'packs/' + now + '_' + file.name
                    filename = default_storage.save(path, file)
                
                source_link = data['source_link']

                # prepare form data so celery can convert it to json
                if data['category']:
                    data['category'] = data['category'].id
                data['tags'] = [tag.id for tag in data['tags']]
                del data['file']

                result = process_pack_upload.delay(data, filename, source_link)
                
                return HttpResponseRedirect(
                    reverse('admin:task_progress_tracker', args=(result.id,))
                )
        else:
            form = PackUploadForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/pack_upload.html', context)

    @button()
    def batch_upload(self, req):
        # for some reason sometimes the dev server would just hang when i
        # uploaded a csv. then i refactored some stuff and it stopped hanging
        # for some reason?
        # i'm worried it'll come back, so just in case it does hang again, i
        # put in these debug logs to see where it does
        logger.debug('entered view')
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = BatchUploadForm(req.POST, req.FILES)
            if form.is_valid():
                logger.debug('validated form')
                file = req.FILES['file']

                logger.debug('before parse')
                try:
                    tasks = self.parse_batch_csv_into_tasks(file)
                except:
                    messages.error(
                        req, 'An error occurred while parsing the CSV.'
                    )
                    context['form'] = BatchUploadForm()
                    return render(req, 'admin/itgdb_site/batch_upload.html', context)
                logger.debug('after parse')
                        
                task_group = group(tasks)
                group_result = task_group.apply_async()
                logger.debug('after task group')
                group_result.save()
                logger.debug('after group save')
                
                return HttpResponseRedirect(
                    reverse('admin:group_progress_tracker', args=(group_result.id,))
                )
        else:
            form = BatchUploadForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/batch_upload.html', context)
    
    @staticmethod
    def parse_batch_csv_into_tasks(csv_file):
        """Parses a batch upload CSV file, and returns a list of Celery task
        signatures that can be run to execute the batch upload."""
        lines = csv_file.read().decode('utf-8').splitlines()
        reader = csv.reader(lines)
        next(reader) # skip header row

        tasks = []
        pack_data_list = []
        for row in reader:
            # process row into a pack_data dict fit for consumption
            # by the celery task

            release_date_year_only = False # default value
            if not row[2]:
                release_date = None
            # first, try parsing as just a release year
            elif row[2].isdigit():
                year = int(row[2])
                release_date = datetime(year, 1, 1, 12, 0, tzinfo=timezone.utc)
                release_date_year_only = True
            else:
                # next, try parsing as a date (datetime will return None)
                release_date = parse_date(row[2])
                if release_date:
                    # if good, set the time to midday utc.
                    # midday utc means the same day in most other parts of
                    # the world, so it'll likely display a consistent date
                    # in the frontend
                    release_date = datetime.combine(release_date, time(12, 0))
                    release_date = make_aware(release_date, timezone.utc)
                else:
                    # now try parsing as a datetime
                    release_date = parse_datetime(row[2])
                    if release_date:
                        # assume datetime is in local timezone
                        release_date = make_aware(release_date)
                    else:
                        # if can't parse as date or datetime, raise error
                        raise ValueError(f'invalid date {row[2]}')

            if row[3]:
                category, _ = PackCategory.objects.get_or_create(
                    name=row[3]
                )
                category_id = category.id
            else:
                category_id = None
            
            if row[4]:
                tag_names = row[4].split(',')
                tag_ids = [
                    Tag.objects.get_or_create(name=name)[0].id
                    for name in tag_names
                ]
            else:
                tag_ids = []
                    
            links = row[6:]
            # remove blank lines
            links = [line for line in links if line]

            pack_data = {
                'name': row[0],
                'author': row[1],
                'release_date': release_date,
                'release_date_year_only': release_date_year_only,
                'category': category_id,
                'tags': tag_ids,
                'links': '\n'.join(links)
            }
            pack_data_list.append(pack_data)

            source_link = row[5]
            if source_link != '(see below)':
                tasks.append(process_pack_from_web.s(pack_data_list, source_link))
                pack_data_list = []
        
        return tasks


@admin.register(Song)
class SongAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    raw_id_fields = ['pack', 'banner', 'bg', 'cdtitle', 'jacket']
    search_fields = ['title']
    list_display = ['title', 'song_actions']
    readonly_fields = ['song_actions']

    def get_urls(self):
        urls = super().get_urls()
        added_urls = [
            path(
                'change_song_date/<int:song_id>',
                self.admin_site.admin_view(self.change_song_date),
                name='change_song_date'
            ),
        ]
        return added_urls + urls
    
    def change_song_date(self, req, song_id):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = ChangeReleaseDateForm(req.POST)
            if form.is_valid():
                new_release_date = form.cleaned_data['new_release_date']
                with transaction.atomic():
                    song = Song.objects.get(pk=song_id)
                    song.release_date = new_release_date
                    song.save()
                    Chart.objects.filter(song__id=song_id).update(
                        release_date=new_release_date
                    )
                messages.success(req,
                    f'Changed release date of {song.title} to {new_release_date}.'
                )
                
                return HttpResponseRedirect(
                    reverse('admin:itgdb_site_song_changelist')
                )
        else:
            form = ChangeReleaseDateForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/change_release_date.html', context)

    @admin.display
    def song_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Set release date</a>',
            reverse('admin:change_song_date', args=(obj.id,))
        )

    @button()
    def update_chart_analyses(self, req):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = UpdateAnalysesForm(req.POST)
            if form.is_valid():
                result = update_analyses.delay(form.cleaned_data)
                return HttpResponseRedirect(
                    reverse('admin:task_progress_tracker', args=(result.id,))
                )
        else:
            form = UpdateAnalysesForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/update_analyses.html', context)


def _get_task_args_display(res):
    if not res:
        return None
    # other task are unsupported right now
    if res.task_name != 'itgdb_site.tasks.process_pack_from_web':
        return None
    args = json.loads(res.task_args)
    m = re.search(r", '([^']*)'\)$", args)
    if not m:
        return json.loads(res.task_args)
    link = m.group(1)
    names = re.findall(r"'name': '((?:[^']|\\')*)'", args)
    return names, link


@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    raw_id_fields = ['song']
    search_fields = ['song__title']


admin.site.unregister(TaskResult)

@admin.register(TaskResult)
class CustomTaskResultAdmin(TaskResultAdmin):
    list_display = ('task_id', 'task_name', 'date_done',
                    'status', 'task_args')
    
    def get_urls(self):
        urls = super(TaskResultAdmin, self).get_urls()
        added_urls = [
            path(
                'progress_tracker/<task_id>',
                self.admin_site.admin_view(self.progress_tracker),
                name='task_progress_tracker'
            ),
        ]
        return added_urls + urls
    
    def progress_tracker(self, req, task_id):
        ctx = self.admin_site.each_context(req)
        ctx['tasks'] = [(task_id, None)]
        return render(req, 'admin/itgdb_site/progress_tracker.html', ctx)


admin.site.unregister(GroupResult)

@admin.register(GroupResult)
class CustomGroupResultAdmin(GroupResultAdmin):
    def get_urls(self):
        urls = super(GroupResultAdmin, self).get_urls()
        added_urls = [
            path(
                'progress_tracker/<group_id>',
                self.admin_site.admin_view(self.progress_tracker),
                name='group_progress_tracker'
            ),
        ]
        return added_urls + urls
    
    def progress_tracker(self, req, group_id):
        ctx = self.admin_site.each_context(req)
        group_result = celery.result.GroupResult.restore(group_id)
        # https://github.com/czue/celery-progress/issues/58#issuecomment-708132745
        task_ids = [
            task
            for parents in group_result.children
            for task in parents.as_list()[::-1]
        ]

        results = TaskResult.objects.filter(task_id__in=task_ids)
        results = {
            res.task_id: res for res in results
        }

        args = map(
            lambda task_id: _get_task_args_display(results.get(task_id)),
            task_ids
        )
        ctx['tasks'] = list(zip(task_ids, args))
        return render(req, 'admin/itgdb_site/progress_tracker.html', ctx)


admin.site.register(Tag)
admin.site.register(ImageFile)
admin.site.register(PackCategory)
