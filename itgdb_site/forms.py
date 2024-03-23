from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column, HTML, Div
from crispy_forms.bootstrap import StrictButton, FieldWithButtons, Accordion, AccordionGroup, PrependedText

from .models import Pack, Tag, PackCategory


ACCORDION_ACTIVE_IGNORE_FIELDS = {'q', 'order_by', 'order_dir'}
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
        fields = ['name', 'release_date', 'category', 'tags', 'links']


class PackSearchForm(forms.Form):
    q = forms.CharField(
        label='',
        required=False,
        max_length=255
    )
    order_by = forms.ChoiceField(
        label='',
        required=False,
        choices={
            'name': 'Pack name',
            'release_date': 'Release date',
            'id': 'Upload date'
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
    steps_type = forms.MultipleChoiceField(
        label='Has steps type:',
        required=False,
        choices=(('1', 'Single'), ('2', 'Double')),
        widget=forms.CheckboxSelectMultiple
    )
    num_charts = forms.FloatField(
        label='At least this many charts per song (on average):',
        required=False,
        min_value=1,
        initial=1
    )
    tags = forms.ModelMultipleChoiceField(
        label='Has any of these tags:',
        required=False,
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.form_class = 'search-form p-2'
        self.helper.layout = Layout(
            Row(
                FieldWithButtons(
                    Field('q', placeholder='Pack name'),
                    StrictButton("Search", type='submit', css_class='btn btn-primary'),
                    input_size="input-group-sm"
                )
            ),
            Row(
                Column(HTML('Order by:'), css_class='col-auto py-1'),
                Column('order_by', css_class='col-auto'),
                Column('order_dir', css_class='col-auto'),
                css_class='g-3'
            ),
            Accordion(
                AccordionGroup('Filters',
                    Row(
                        Column('category'),
                        Column('steps_type'),
                        Column('num_charts', css_class='pe-5'),
                        Column('tags')
                    ),
                    active=_get_filter_accordion_active_status(self)
                )
            )
        )


class SongSearchForm(forms.Form):
    q = forms.CharField(
        label='',
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Pack name'})
    )
    search_by = forms.ChoiceField(
        label='',
        required=True,
        choices={
            'titleartist': 'Title/artist',
            'title': 'Title',
            'artist': 'Artist',
        },
        initial='titleartist'
    )
    steps_type = forms.MultipleChoiceField(
        label='Has steps type:',
        required=False,
        choices=(('1', 'Single'), ('2', 'Double')),
        widget=forms.CheckboxSelectMultiple
    )
    diffs = forms.MultipleChoiceField(
        label='Has difficulties:',
        required=False,
        choices=(
            ('0', 'Novice'),
            ('1', 'Easy'),
            ('2', 'Medium'),
            ('3', 'Hard'),
            ('4', 'Expert')
        ),
        widget=forms.CheckboxSelectMultiple
    )
    tags = forms.ModelMultipleChoiceField(
        label='Pack has tags:',
        required=False,
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )