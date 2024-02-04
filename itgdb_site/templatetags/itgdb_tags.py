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
def chart_tooltip(chart):
    lines = []
    for line in (chart.credit, chart.description, chart.chart_name):
        if line and line not in lines:
            lines.append(line)
    tooltip = '<br />'.join(map(escape, lines))
    return f'{tooltip}'