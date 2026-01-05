import re
from django import template
from django.utils.html import escape
from django.template.defaultfilters import date as date_filter

register = template.Library()

def _get_chart_desc_lines(chart):
    lines = []
    for line in (chart.credit, chart.description, chart.chart_name):
        if line and line not in lines:
            lines.append(line)
    return lines

@register.filter
def duration(value):
    value = round(value)
    h = value // 3600
    m = (value % 3600) // 60
    s = (value % 60)
    if h > 0:
        return '%d:%02d:%02d' % (h, m, s)
    return '%d:%02d' % (m, s)

@register.filter
def display_bpm(song):
    if song.min_display_bpm is None or song.max_display_bpm is None:
        return '?'
    elif song.min_display_bpm == song.max_display_bpm:
        return str(round(song.min_display_bpm))
    return '%d-%d' % (round(song.min_display_bpm), round(song.max_display_bpm))

@register.filter
def chart_tooltip(chart):
    lines = _get_chart_desc_lines(chart)
    return '<br />'.join(map(escape, lines))

@register.filter
def chart_desc_display(chart):
    lines = _get_chart_desc_lines(chart)
    for i, line in enumerate(lines):
        line = escape(line)
        if i > 0:
            line = f'<span class="text-muted">{line}</span>'
        lines[i] = line
    return '<br />'.join(lines)

@register.filter
def chart_diff_short(chart):
    steps_type_mapping = {1: 'S', 2: 'D'}
    diff_mapping = ['N', 'E', 'M', 'H', 'X', 'Ed']
    return steps_type_mapping[chart.steps_type] + \
        diff_mapping[chart.difficulty]

@register.filter
def chart_diff_long(chart):
    steps_type_mapping = {1: 'Single', 2: 'Double'}
    diff_mapping = ['Novice', 'Easy', 'Medium', 'Hard', 'Expert', 'Edit']
    return steps_type_mapping[chart.steps_type] + ' ' + \
        diff_mapping[chart.difficulty]

@register.filter
def release_date(obj):
    if obj.release_date_year_only:
        return str(obj.release_date.year)
    return date_filter(obj.release_date, 'M j, Y')

# https://stackoverflow.com/questions/48482319/django-pagination-url
PAGE_NUMBER_REGEX = re.compile(r'(page=[0-9]*[\&]*)')
@register.simple_tag  
def append_page_param(value, page_num=None):
    value = re.sub(PAGE_NUMBER_REGEX, '', value)
    if page_num:
        if not '?' in value:
            value += f'?page={page_num}'
        elif value[-1] != '&':
            value += f'&page={page_num}'
        else:
            value += f'page={page_num}'
    return value