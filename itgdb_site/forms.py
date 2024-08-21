from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column, HTML, Fieldset
from crispy_forms.bootstrap import StrictButton, FieldWithButtons, Accordion, AccordionGroup, PrependedText

from .models import Pack, Tag, PackCategory


ACCORDION_ACTIVE_IGNORE_FIELDS = {'q', 'order_by', 'order_dir', 'search_by'}
def _get_filter_accordion_active_status(form: forms.Form):
    if form.is_bound and form.is_valid():
        for k, v in form.cleaned_data.items():
            if k not in ACCORDION_ACTIVE_IGNORE_FIELDS and v:
                return True
    return False


class PackUploadForm(forms.ModelForm):
    file = forms.FileField(label='Pack file')

    class Meta:
        model = Pack
        fields = ['name', 'author', 'release_date', 'category', 'tags', 'links']


class BatchUploadForm(forms.Form):
    file = forms.FileField(label='CSV file')


class UpdateAnalysesForm(forms.Form):
    which = forms.MultipleChoiceField(
        label='Choose which fields to update:',
        choices={
            'chart_length': 'chart_length',
            'stream_info': 'stream_info',
            'counts': 'counts'
        }
    )


class PackSearchForm(forms.Form):
    q = forms.CharField(
        label='',
        required=False,
        max_length=255
    )
    search_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'name': 'Pack name',
            'author': 'Pack author(s)'
        }
    )
    order_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'name': 'Pack name',
            'release_date': 'Release date',
            'upload_date': 'Upload date'
        }
    )
    order_dir = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'asc': 'Ascending',
            'desc': 'Descending',
        }
    )
    category = forms.ModelChoiceField(
        label='Category:',
        required=False,
        queryset=PackCategory.objects.order_by('name')
    )
    steps_type = forms.TypedMultipleChoiceField(
        label='Has steps type:',
        required=False,
        choices=((1, 'Single'), (2, 'Double')),
        coerce=int,
        empty_value=[],
        widget=forms.CheckboxSelectMultiple
    )
    num_singles_charts = forms.FloatField(
        label='', required=False,
        min_value=1, initial=1
    )
    num_doubles_charts = forms.FloatField(
        label='', required=False,
        min_value=1, initial=1
    )
    tags = forms.ModelMultipleChoiceField(
        label='Has all of these tags:',
        required=False,
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )
    min_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )
    max_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.form_class = 'search-form p-2'
        self.helper.layout = Layout(
            Row(
                Column(Field('search_by'), css_class='col-2', style="min-width: 10em;"),
                Column(FieldWithButtons(
                    Field('q'),
                    StrictButton("Search", type='submit', css_class='btn btn-primary'),
                    input_size="input-group-sm",
                ), css_class='col'),
                css_class='g-2'
            ),
            Row(
                Column(HTML('Order by:'), css_class='col-auto py-1'),
                Column('order_by', css_class='col-auto'),
                Column('order_dir', css_class='col-auto'),
                css_class='g-2 flex-nowrap'
            ),
            Accordion(AccordionGroup('Filters',
                Row(
                    Column('category'),
                    Column('steps_type'),
                    Column('tags')
                ),
                Row(
                    Column(Fieldset('Avg. # of charts per song:', Row(
                        Column(
                            Field('num_singles_charts', placeholder='Singles'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('num_doubles_charts', placeholder='Doubles'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                    Column(Fieldset('Release date (from/to):', Row(
                        Column(
                            Field('min_release_date'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_release_date'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                ),
                active=_get_filter_accordion_active_status(self)
            ))
        )


class SongSearchForm(forms.Form):
    q = forms.CharField(
        label='',
        required=False,
        max_length=255
    )
    search_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'titleartist': 'Title/artist',
            'title': 'Title',
            'artist': 'Artist'
        }
    )
    order_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'title': 'Title',
            'release_date': 'Release date',
            'upload_date': 'Upload date'
        }
    )
    order_dir = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'asc': 'Ascending',
            'desc': 'Descending',
        }
    )
    category = forms.ModelChoiceField(
        label='Pack category:',
        required=False,
        queryset=PackCategory.objects.order_by('name')
    )
    min_length = forms.FloatField(
        label='', required=False, min_value=0
    )
    max_length = forms.FloatField(
        label='', required=False, min_value=0
    )
    min_bpm = forms.FloatField(
        label='', required=False
    )
    max_bpm = forms.FloatField(
        label='', required=False
    )
    min_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )
    max_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.form_class = 'search-form p-2'
        self.helper.layout = Layout(
            Row(
                Column(Field('search_by'), css_class='col-2', style="min-width: 8.5em;"),
                Column(FieldWithButtons(
                    Field('q'),
                    StrictButton("Search", type='submit', css_class='btn btn-primary'),
                    input_size="input-group-sm",
                ), css_class='col'),
                css_class='g-2'
            ),
            Row(
                Column(HTML('Order by:'), css_class='col-auto py-1'),
                Column('order_by', css_class='col-auto'),
                Column('order_dir', css_class='col-auto'),
                css_class='g-2 flex-nowrap'
            ),
            Accordion(AccordionGroup('Filters',
                Row(
                    Column('category'),
                    Column(Fieldset('Length (seconds):', Row(
                        Column(
                            Field('min_length', placeholder='Min'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_length', placeholder='Max'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                ),
                Row(
                    Column(Fieldset('Release date (from/to):', Row(
                        Column(
                            Field('min_release_date'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_release_date'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                    Column(Fieldset('BPM:', Row(
                        Column(
                            Field('min_bpm', placeholder='Min'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_bpm', placeholder='Max'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                ),
                active=_get_filter_accordion_active_status(self)
            ))
        )


class ChartSearchForm(forms.Form):
    q = forms.CharField(
        label='',
        required=False,
        max_length=255
    )
    search_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'titleartist': 'Title/artist',
            'title': 'Title',
            'artist': 'Artist',
            'desc': 'Description',
            'hash': 'Chart hash',
        }
    )
    order_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'title': 'Title',
            'release_date': 'Release date'
        }
    )
    order_dir = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'asc': 'Ascending',
            'desc': 'Descending',
        }
    )
    category = forms.ModelChoiceField(
        label='Pack category:',
        required=False,
        queryset=PackCategory.objects.order_by('name')
    )
    min_length = forms.FloatField(
        label='', required=False, min_value=0
    )
    max_length = forms.FloatField(
        label='', required=False, min_value=0
    )
    min_bpm = forms.FloatField(
        label='', required=False
    )
    max_bpm = forms.FloatField(
        label='', required=False
    )
    steps_type = forms.TypedChoiceField(
        label='Steps type:',
        required=False,
        choices=(('', '---------'), (1, 'Single'), (2, 'Double')),
        coerce=int
    )
    diff = forms.TypedMultipleChoiceField(
        label='Difficulty slot:',
        required=False,
        choices=(
            (0, 'Novice'), (1, 'Easy'), (2, 'Medium'),
            (3, 'Hard'), (4, 'Expert'), (5, 'Edit')
        ),
        coerce=int,
        empty_value=[],
        widget=forms.CheckboxSelectMultiple
    )
    min_meter = forms.IntegerField(
        label='', required=False, min_value=1
    )
    max_meter = forms.IntegerField(
        label='', required=False, min_value=1
    )
    min_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )
    max_release_date = forms.DateField(
        label='', required=False,
        widget=forms.TextInput(attrs={'type': 'date'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.form_class = 'search-form p-2'
        self.helper.layout = Layout(
            Row(
                Column(Field('search_by'), css_class='col-2', style="min-width: 8.5em;"),
                Column(FieldWithButtons(
                    Field('q'),
                    StrictButton("Search", type='submit', css_class='btn btn-primary'),
                    input_size="input-group-sm",
                ), css_class='col'),
                css_class='g-2'
            ),
            Row(
                Column(HTML('Order by:'), css_class='col-auto py-1'),
                Column('order_by', css_class='col-auto'),
                Column('order_dir', css_class='col-auto'),
                css_class='g-2 flex-nowrap'
            ),
            Accordion(AccordionGroup('Filters',
                Row(
                    Column('category'),
                    Column(Fieldset('Length (seconds):',Row(
                        Column(
                            Field('min_length', placeholder='Min'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_length', placeholder='Max'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                    Column(Fieldset('BPM:', Row(
                        Column(
                            Field('min_bpm', placeholder='Min'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_bpm', placeholder='Max'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                ),
                Row(
                    Column('steps_type'),
                    Column(Fieldset('Difficulty:', Row(
                        Column(
                            Field('min_meter', placeholder='Min'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_meter', placeholder='Max'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                    Column(Fieldset('Release date (from/to):', Row(
                        Column(
                            Field('min_release_date'),
                            css_class='col-6'
                        ),
                        Column(
                            Field('max_release_date'),
                            css_class='col-6'
                        ),
                        css_class='g-2'
                    ))),
                ),
                Row(
                    Column('diff'),
                ),
                active=_get_filter_accordion_active_status(self)
            ))
        )
