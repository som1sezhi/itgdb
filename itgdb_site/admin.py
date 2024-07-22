from datetime import datetime
import csv
import json
from django.contrib import admin
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.urls import re_path, path, reverse
from admin_extra_buttons.api import ExtraButtonsMixin, button
from django_celery_results.admin import TaskResultAdmin, GroupResultAdmin
from django_celery_results.models import TaskResult, GroupResult
from celery import group
import celery.result
from celery_progress.backend import Progress

from .models import Tag, Pack, Song, Chart, ImageFile, PackCategory
from .forms import PackUploadForm, BatchUploadForm
from .tasks import process_pack_upload, process_batch_upload, test_task

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
                process_pack_upload.delay(data, filename)
                return HttpResponseRedirect('/admin/itgdb_site/pack/')
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
                form_data = form.cleaned_data
                file = form_data['file']
                now = datetime.now().strftime('%Y%m%d%H%M%S')
                path = 'packs/' + now + '_' + file.name
                filename = default_storage.save(path, file)

                process_batch_upload.delay(filename)
                return HttpResponseRedirect('/admin/itgdb_site/pack/')
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
                    print(row)
                    tasks.append(test_task.s(int(row['time'])))
                task_group = group(tasks)
                group_result = task_group.apply_async()
                group_result.save()

                context['task_id'] = group_result.id
                
                return HttpResponseRedirect(
                    reverse('admin:progress_tracker', args=(group_result.id,))
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

admin.site.unregister(GroupResult)

@admin.register(GroupResult)
class CustomGroupResultAdmin(GroupResultAdmin):

    def get_urls(self):
        urls = super(GroupResultAdmin, self).get_urls()
        added_urls = [
            path(
                'progress_tracker/<group_id>',
                self.admin_site.admin_view(self.progress_tracker),
                name='progress_tracker'
            ),
            path(
                'progress/<group_id>',
                self.get_progress,
                name='progress'
            ),
        ]
        return added_urls + urls
    
    def progress_tracker(self, req, group_id):
        ctx = self.admin_site.each_context(req)
        group_result = celery.result.GroupResult.restore(group_id)
        print(group_result.children)
        ctx['group_id'] = group_id
        # https://github.com/czue/celery-progress/issues/58#issuecomment-708132745
        ctx['task_ids'] = [
            task
            for parents in group_result.children
            for task in parents.as_list()[::-1]
        ]
        return render(req, 'admin/itgdb_site/progress_tracker.html', ctx)
    
    def get_progress(self, req, group_id):
        group_result = celery.result.GroupResult.restore(group_id)
        task_ids = [
            task
            for parents in group_result.children
            for task in parents.as_list()[::-1]
        ]
        data = [
            Progress(celery.result.AsyncResult(task_id)).get_info()
            for task_id in task_ids
        ]
        return HttpResponse(json.dumps(data), content_type='application/json')


admin.site.register(Song)
admin.site.register(Chart)
admin.site.register(Tag)
admin.site.register(ImageFile)
admin.site.register(PackCategory)
