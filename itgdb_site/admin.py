from datetime import datetime
from django.contrib.admin import AdminSite
from django.core import serializers
from django.core.files.storage import default_storage
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path

from .models import Tag, Pack, Song, Chart
from .forms import PackUploadForm
from .tasks import process_pack_upload

class ItgdbAdminSite(AdminSite):
    site_header = 'yeah woo'

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('pack_upload/', self.admin_view(self.pack_upload_view))
        ]
        return my_urls + urls
    
    def pack_upload_view(self, req):
        if req.method == 'POST':
            form = PackUploadForm(req.POST, req.FILES)
            if form.is_valid():
                form_data = form.cleaned_data
                file = form_data['file']
                now = datetime.now().strftime('%Y%m%d%H%M%S')
                path = 'packs/' + now + '_' + file.name
                filename = default_storage.save(path, file)
                print(form_data)
                print(filename)

                # prepare form data so celery can convert it to json
                data = form.cleaned_data
                data['tags'] = [tag.id for tag in data['tags']]
                del data['file']
                process_pack_upload.delay(data, filename)
                return HttpResponseRedirect('/admin/')
        else:
            form = PackUploadForm()
        context = dict(
            self.each_context(req),
            text='hello',
            form=form
        )
        return render(req, 'admin/itgdb_site/pack_upload.html', context)



admin_site = ItgdbAdminSite()
admin_site.register(Pack)
admin_site.register(Song)
admin_site.register(Chart)
admin_site.register(Tag)