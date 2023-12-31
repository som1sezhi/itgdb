from django import forms
from django.core import serializers

from .models import Pack


class PackUploadForm(forms.ModelForm):
    file = forms.FileField(label='Pack file')

    class Meta:
        model = Pack
        fields = ['name', 'release_date', 'tags']
