from datetime import datetime, timezone, time
import csv
import logging
from django.contrib import admin
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.urls import re_path, path, reverse
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.timezone import make_aware, now
from django.contrib import messages
from admin_extra_buttons.api import ExtraButtonsMixin, button
from django_celery_results.admin import TaskResultAdmin, GroupResultAdmin
from django_celery_results.models import TaskResult, GroupResult
from celery import group
import celery.result

from .models import Tag, Pack, Song, Chart, ImageFile, PackCategory
from .forms import PackUploadForm, BatchUploadForm, UpdateAnalysesForm
from .tasks import process_pack_upload, process_pack_from_web, update_analyses

logger = logging.getLogger(__name__)


@admin.register(Pack)
class PackAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    @button()
    def pack_upload(self, req):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = PackUploadForm(req.POST, req.FILES)
            if form.is_valid():
                form_data = form.cleaned_data
                file = form_data['file']
                now = datetime.now().strftime('%Y%m%d%H%M%S')
                path = 'packs/' + now + '_' + file.name
                filename = default_storage.save(path, file)

                # prepare form data so celery can convert it to json
                data = form.cleaned_data
                if data['category']:
                    data['category'] = data['category'].id
                data['tags'] = [tag.id for tag in data['tags']]
                del data['file']

                result = process_pack_upload.delay(data, filename)
                
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

            if not row[2]:
                release_date = None
            else:
                # first, try parsing as a date (datetime will return None)
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
        ctx['task_ids'] = [task_id]
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
        ctx['task_ids'] = [
            task
            for parents in group_result.children
            for task in parents.as_list()[::-1]
        ]
        return render(req, 'admin/itgdb_site/progress_tracker.html', ctx)


admin.site.register(Chart)
admin.site.register(Tag)
admin.site.register(ImageFile)
admin.site.register(PackCategory)
