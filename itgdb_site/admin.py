from datetime import datetime, timezone
import csv
from django.contrib import admin
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.urls import re_path, path, reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
from admin_extra_buttons.api import ExtraButtonsMixin, button
from django_celery_results.admin import TaskResultAdmin, GroupResultAdmin
from django_celery_results.models import TaskResult, GroupResult
from celery import group
import celery.result

from .models import Tag, Pack, Song, Chart, ImageFile, PackCategory
from .forms import PackUploadForm, BatchUploadForm
from .tasks import process_pack_upload, process_pack_from_web, test_task


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
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = BatchUploadForm(req.POST, req.FILES)
            if form.is_valid():
                file = req.FILES['file']
                lines = file.read().decode('utf-8').splitlines()
                reader = csv.reader(lines)
                next(reader) # skip header row

                tasks = []
                pack_data_list = []
                for row in reader:
                    # process row into a pack_data dict fit for consumption
                    # by the celery task

                    # first, try parsing as a datetime
                    release_date = parse_datetime(row[2])
                    if release_date:
                        # assume this is in local timezone
                        release_date = make_aware(release_date)
                    else:
                        # try parsing as just a date (with specified
                        # time of midday)
                        release_date = parse_datetime(row[2] + ' 12:00')
                        if release_date:
                            # midday utc means the same day in most other parts
                            # of the world
                            release_date = make_aware(
                                release_date, timezone.utc
                            )

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
                    # remove first line from links if blank
                    if links and not links[0]:
                        links.pop(0)

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
                        
                task_group = group(tasks)
                group_result = task_group.apply_async()
                group_result.save()
                
                return HttpResponseRedirect(
                    reverse('admin:group_progress_tracker', args=(group_result.id,))
                )
        else:
            form = BatchUploadForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/batch_upload.html', context)
    
    @button()
    def group_test(self, req):
        context = self.get_common_context(req)
        if req.method == 'POST':
            form = BatchUploadForm(req.POST, req.FILES)
            if form.is_valid():
                file = req.FILES['file']
                lines = file.read().decode('utf-8').splitlines()
                tasks = []
                reader = csv.DictReader(lines, fieldnames=['time'])
                for row in reader:
                    tasks.append(test_task.s(int(row['time'])))
                task_group = group(tasks)
                group_result = task_group.apply_async()
                group_result.save()
                
                return HttpResponseRedirect(
                    reverse('admin:group_progress_tracker', args=(group_result.id,))
                )
        else:
            form = BatchUploadForm()
        context['form'] = form
        return render(req, 'admin/itgdb_site/batch_upload.html', context)


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


admin.site.register(Song)
admin.site.register(Chart)
admin.site.register(Tag)
admin.site.register(ImageFile)
admin.site.register(PackCategory)
