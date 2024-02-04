from typing import Any
from django.db.models import Case, When, CharField, Count, Sum
from django.db.models.functions import Coalesce, Upper
from django.views import generic

from .models import Pack, Song, Chart


class IndexView(generic.ListView):
    template_name = 'itgdb_site/index.html'
    context_object_name = 'latest_uploaded_packs'

    def get_queryset(self):
        return Pack.objects.order_by('-id')[:8]


class PackDetailView(generic.DetailView):
    model = Pack
    template_name = 'itgdb_site/pack_detail.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        songs = self.object.song_set.annotate(
            title_sort=Coalesce(
                Case(
                    When(title_translit__exact='', then=None),
                    default=Upper('title_translit'),
                    output_field=CharField()
                ),
                Upper('title')
            )
        ).order_by('title_sort').prefetch_related('chart_set', 'banner')
        ctx['songs'] = songs

        charts = Chart.objects.filter(song__pack=self.object)
        ctx['chart_count'] = charts.count()

        # count how many charts are there for each meter/difficulty/stepstype
        # so we can put the counts in a cool graph
        diff_counts_queryset = charts.values(
            'steps_type', 'difficulty', 'meter'
        ).annotate(count=Count('meter'))

        diff_counts = {k: {'all': {}} for k in Chart.STEPS_TYPE_CHOICES}
        for entry in diff_counts_queryset:
            steps_type = entry['steps_type']
            diff = entry['difficulty']
            meter = entry['meter']
            count = entry['count']
            if diff not in diff_counts[steps_type]:
                diff_counts[steps_type][diff] = {}
            diff_counts[steps_type][diff][meter] = count
            if meter not in diff_counts[steps_type]['all']:
                diff_counts[steps_type]['all'][meter] = 0
            diff_counts[steps_type]['all'][meter] += count

        diff_to_name = {
            0: 'Novice',
            1: 'Easy',
            2: 'Medium',
            3: 'Hard',
            4: 'Expert',
            5: 'Edit'
        }
        difficulty_data = {}
        for steps_type, counts_by_diff in diff_counts.items():
            meters = sorted(list(counts_by_diff['all'].keys()))
            # figure out the meter labels.
            # we want them to be contiguous ranges most of the time,
            # but if there's too big a gap then we can skip some
            if meters:
                labels = [meters[0]]
                for i in range(1, len(meters)):
                    m = meters[i]
                    prev_m = meters[i - 1]
                    if m - prev_m <= 5:
                        labels.extend(range(prev_m + 1, m + 1))
                    else:
                        labels.append(m)
            else:
                labels = []
            datasets = [
                {
                    'diff_num': diff,
                    'label': diff_to_name[diff],
                    'data': [
                        counts_by_diff[diff].get(m, 0) for m in labels
                    ]
                }
                for diff in counts_by_diff
                if diff != 'all'
            ]
            datasets.sort(key=lambda v: v['diff_num'])
            difficulty_data[steps_type] = {
                'labels': labels,
                'datasets': datasets
            }

        ctx['difficulty_data'] = difficulty_data

        return ctx