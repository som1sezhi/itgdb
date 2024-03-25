from datetime import datetime
from django.contrib import admin
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect
from django.shortcuts import render
from admin_extra_buttons.api import ExtraButtonsMixin, button
from django_celery_results.admin import TaskResultAdmin
from django_celery_results.models import TaskResult

from .models import Tag, Pack, Song, Chart, ImageFile, PackCategory
from .forms import PackUploadForm
from .tasks import process_pack_upload

@admin.register(Pack)
class TestModelAdmin(ExtraButtonsMixin, admin.ModelAdmin):
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


admin.site.unregister(TaskResult)

@admin.register(TaskResult)
class CustomTaskResultAdmin(TaskResultAdmin):
    list_display = ('task_id', 'task_name', 'date_done',
                    'status', 'task_args')

admin.site.register(Song)
admin.site.register(Chart)
admin.site.register(Tag)
admin.site.register(ImageFile)
admin.site.register(PackCategory)
