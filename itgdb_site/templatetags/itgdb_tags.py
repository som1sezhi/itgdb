from django import template
from django.utils.html import escape

register = template.Library()

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
    if not song.min_display_bpm or not song.max_display_bpm:
        return '?'
    elif song.min_display_bpm == song.max_display_bpm:
        return str(round(song.min_display_bpm))
    return '%d-%d' % (round(song.min_display_bpm), round(song.max_display_bpm))

@register.filter
def chart_tooltip(chart):
    lines = []
    for line in (chart.credit, chart.description, chart.chart_name):
        if line and line not in lines:
            lines.append(line)
    tooltip = '<br />'.join(map(escape, lines))
    return f'{tooltip}'

@register.filter
def chart_diff_short(chart):
    steps_type_mapping = {1: 'S', 2: 'D'}
    diff_mapping = ['N', 'E', 'M', 'H', 'X', 'Ed']
    return steps_type_mapping[chart.steps_type] + \
        diff_mapping[chart.difficulty]