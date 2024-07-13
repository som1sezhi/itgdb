from typing import Any
from django.db.models import Case, When, CharField, Count, Min, Max, F, FloatField, Value
from django.db.models.functions import Coalesce, Upper, Cast
from django.db.models.query import QuerySet
from django.views import generic
from django.contrib.postgres.search import SearchVector, SearchQuery

from .models import Pack, Song, Chart
from .forms import PackSearchForm, SongSearchForm, ChartSearchForm


def _create_links_iterable(links: str):
    '''Given the contents of a links field, parse it into an iterable
    of (link label, link URL) pairs.
    '''
    # A links field shall be a series of alternating link labels and URLs,
    # separated by line breaks. If there are an odd number of lines,
    # add an implicit 'Download' label for the first link.
    links_lines = links.splitlines()
    if len(links_lines) % 2 == 1:
        links_lines.insert(0, 'Download')
    return zip(links_lines[::2], links_lines[1::2])


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

        ctx['links'] = _create_links_iterable(self.object.links)

        charts = Chart.objects.filter(song__pack=self.object)
        ctx['chart_count'] = charts.count()

        ctx['show_double_nov'] = charts.filter(
            steps_type=2, difficulty=0
        ).exists()

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


class SongDetailView(generic.DetailView):
    model = Song
    template_name = 'itgdb_site/song_detail.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        charts = self.object.chart_set.order_by('steps_type', 'difficulty')
        ctx['density_data'] = [
            {
                'id': chart.id,
                'diff_num': chart.difficulty,
                'points': chart.density_graph,
                'peak_nps': max(p[1] for p in chart.density_graph)
            }
            for chart in charts
        ]
        ctx['links'] = _create_links_iterable(self.object.links)
        ctx['charts'] = list(zip(charts, ctx['density_data']))

        # for some reason, using firstof in the django template breaks things
        # with sorl-thumbnail, so instead we decide which background image to
        # use in here.
        if self.object.bg:
            ctx['bg_img'] = self.object.bg.image
        elif self.object.banner:
            ctx['bg_img'] = self.object.banner.image

        return ctx


class PackSearchView(generic.ListView):
    template_name = 'itgdb_site/pack_search.html'
    context_object_name = 'packs'
    paginate_by = 50 # TODO: change to reasonable number after testing

    def get_queryset(self):
        form = PackSearchForm(self.request.GET)
        if form.is_valid():
            try:
                q = form.cleaned_data['q']
                category = form.cleaned_data['category']
                steps_types = list(map(int, form.cleaned_data['steps_type']))
                num_charts = form.cleaned_data['num_charts']
                tags = form.cleaned_data['tags']

                qset = Pack.objects.filter(name__icontains=q)
                
                qset = qset.annotate(
                    song_count=Count('song', distinct=True)
                )

                if category:
                    qset = qset.filter(category=category)
                
                if steps_types:
                    qset = qset.filter(song__chart__steps_type__in=steps_types) \
                        .annotate(num_steps_type=Count('song__chart__steps_type', distinct=True)) \
                        .filter(num_steps_type=len(steps_types)) \
                        .distinct()
                
                if num_charts:
                    qset = qset.annotate(
                        avg_num_charts=Cast(
                            Count('song__chart', distinct=True), FloatField()
                        ) / Cast('song_count', FloatField())
                    ).filter(
                        avg_num_charts__gte=num_charts
                    ).distinct()
                
                if tags:
                    qset = qset.filter(tags__in=form.cleaned_data['tags']).distinct()
                
                # perform ordering
                if form.cleaned_data['order_by']:
                    if form.cleaned_data['order_by'] == 'name':
                        # do case-insensitive sort
                        order_field = Upper('name')
                    else:
                        order_field = F(form.cleaned_data['order_by'])
                else:
                    order_field = Upper('name')
                if form.cleaned_data['order_dir'] == 'desc':
                    order_field = order_field.desc(nulls_last=True)
                else:
                    order_field = order_field.asc(nulls_last=True)
                qset = qset.order_by(order_field)

            # i actually forgot what this was supposed to catch lol
            except ValueError:
                qset = Pack.objects.annotate(
                    song_count=Count('song', distinct=True)
                ).order_by(Upper('name'))
        else:
            qset = Pack.objects.annotate(
                song_count=Count('song', distinct=True)
            ).order_by(Upper('name'))

        return qset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        # do we need to create the PackSearchForm twice?
        ctx['form'] = PackSearchForm(self.request.GET)

        packs = ctx['packs']
        packs = packs.select_related('banner').prefetch_related('tags')

        # fetch per-pack difficulty count data.
        # should probably note that strictly speaking, this counts the
        # number of charts in each diff slot, not the number of songs with
        # that diff slot, even though i often treat it like the latter.
        # thus in the case of multiple edit charts, stuff may look technically
        # incorrect, but i feel like the cases where that matters will be
        # super rare, so i'll just leave it like this
        charts = Chart.objects.filter(song__pack__in=packs)
        diff_counts_queryset = charts.values(
            'song__pack__id', 'steps_type', 'difficulty',
        ).annotate(
            min=Min('meter'),
            max=Max('meter'),
            count=Count('difficulty')
        )
        # organize the data into a dict
        diff_data = {}
        for entry in diff_counts_queryset:
            pack_id = entry['song__pack__id']
            steps_type = entry['steps_type']
            diff = entry['difficulty']
            diff_data[(pack_id, steps_type, diff)] = {
                'steps_type': steps_type,
                'diff': diff,
                'min_meter': entry['min'],
                'max_meter': entry['max'],
                'song_count': entry['count'],
            }
        # grab the data from the dict in steps_type+diff order
        # so the template can just iterate through it.
        # also figure out if we need to display the double nov column
        ctx['show_double_nov'] = False
        for pack in packs:
            data = []
            for steps_type in Chart.STEPS_TYPE_CHOICES:
                for diff in Chart.DIFFICULTY_CHOICES:
                    key = (pack.id, steps_type, diff)
                    if key in diff_data:
                        data.append(diff_data[key])
                        if steps_type == 2 and diff == 0:
                            ctx['show_double_nov'] = True
                    else:
                        data.append({
                            'steps_type': steps_type,
                            'diff': diff,
                            'song_count': 0
                        })
            pack.diff_data = data
        
        ctx['packs'] = packs

        ctx['page_range'] = ctx['paginator'].get_elided_page_range(
            ctx['page_obj'].number, on_each_side=2, on_ends=1
        )

        return ctx


class SongSearchView(generic.ListView):
    template_name = 'itgdb_site/song_search.html'
    context_object_name = 'songs'
    paginate_by = 50
    
    def get_queryset(self) -> QuerySet[Song]:
        form = SongSearchForm(self.request.GET)
        if form.is_valid():
            q = form.cleaned_data['q']
            search_by = form.cleaned_data['search_by']
            category = form.cleaned_data['category']
            min_length = form.cleaned_data['min_length']
            max_length = form.cleaned_data['max_length']
            min_bpm = form.cleaned_data['min_bpm']
            max_bpm = form.cleaned_data['max_bpm']

            if q:
                search_vec_title_fields = [
                    'title', 'subtitle', 'title_translit', 'subtitle_translit'
                ]
                search_vec_artist_fields = [
                    'artist', 'artist_translit',
                ]
                if search_by == 'title':
                    search_vec_args = search_vec_title_fields
                elif search_by == 'artist':
                    search_vec_args = search_vec_artist_fields
                else: # search_by == titleartist
                    search_vec_args = \
                        search_vec_title_fields + search_vec_artist_fields
                
                qset = Song.objects.annotate(search=SearchVector(
                    *search_vec_args,
                    config='public.itgdb_search'
                )).filter(search=SearchQuery(
                    q, search_type='websearch', config='public.itgdb_search'
                ))
            else:
                qset = Song.objects.all()

            if category:
                qset = qset.filter(pack__category=category)
            
            if min_length:
                qset = qset.filter(length__gte=min_length)
            if max_length:
                qset = qset.filter(length__lte=max_length)
            if min_bpm:
                qset = qset.filter(min_display_bpm__gte=min_bpm)
            if max_bpm:
                qset = qset.filter(max_display_bpm__lte=max_bpm)

            # perform ordering
            if form.cleaned_data['order_by']:
                if form.cleaned_data['order_by'] == 'title':
                    # do case-insensitive sort
                    order_field = Upper('title')
                else:
                    order_field = F(form.cleaned_data['order_by'])
            else:
                order_field = Upper('title')
            if form.cleaned_data['order_dir'] == 'desc':
                order_field = order_field.desc(nulls_last=True)
            else:
                order_field = order_field.asc(nulls_last=True)
            qset = qset.order_by(order_field)

        else:
            qset = Song.objects.order_by(Upper('title'))

        return qset
    
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        ctx['form'] = SongSearchForm(self.request.GET)

        ctx['songs'] = ctx['songs'] \
            .select_related('pack__category') \
            .prefetch_related('chart_set', 'banner')
        
        # iterate through charts manually to determine existence of a doubles
        # novice chart. hopefully this takes advantage of prefetching so
        # we can avoid having to hit the database
        ctx['show_double_nov'] = False
        for song in ctx['songs']:
            for chart in song.chart_set.all():
                if chart.steps_type == 2 and chart.difficulty == 0:
                    ctx['show_double_nov'] = True
                    break
            if ctx['show_double_nov']:
                break

        ctx['page_range'] = ctx['paginator'].get_elided_page_range(
            ctx['page_obj'].number, on_each_side=2, on_ends=1
        )

        return ctx


class ChartSearchView(generic.ListView):
    template_name = 'itgdb_site/chart_search.html'
    context_object_name = 'charts'
    paginate_by = 50
    
    def get_queryset(self) -> QuerySet[Song]:
        form = ChartSearchForm(self.request.GET)
        if form.is_valid():
            print(form.cleaned_data)
            data = form.cleaned_data
            q = data['q']
            search_by = data['search_by']

            if q:
                if search_by == 'hash':
                    qset = Chart.objects.filter(chart_hash__istartswith=q)
                else:
                    search_vec_title_fields = [
                        'song__title', 'song__subtitle',
                        'song__title_translit', 'song__subtitle_translit'
                    ]
                    search_vec_artist_fields = [
                        'song__artist', 'song__artist_translit',
                    ]
                    if search_by == 'title':
                        search_vec_args = search_vec_title_fields
                    elif search_by == 'artist':
                        search_vec_args = search_vec_artist_fields
                    elif search_by == 'desc':
                        search_vec_args = [
                            'credit', 'description', 'chart_name'
                        ]
                    else: # search_by == titleartist
                        search_vec_args = \
                            search_vec_title_fields + search_vec_artist_fields
                    
                    qset = Chart.objects.annotate(search=SearchVector(
                        *search_vec_args,
                        config='public.itgdb_search'
                    )).filter(search=SearchQuery(
                        q, search_type='websearch', config='public.itgdb_search'
                    ))
            else:
                qset = Chart.objects.all()

            if data['category']:
                qset = qset.filter(song__pack__category=data['category'])
            
            if data['min_length']:
                qset = qset.filter(song__length__gte=data['min_length'])
            if data['max_length']:
                qset = qset.filter(song__length__lte=data['max_length'])
            if data['min_bpm']:
                qset = qset.filter(song__min_display_bpm__gte=data['min_bpm'])
            if data['max_bpm']:
                qset = qset.filter(song__max_display_bpm__lte=data['max_bpm'])
            
            if data['steps_type']:
                qset = qset.filter(steps_type=data['steps_type'])
            if data['diff']:
                qset = qset.filter(difficulty__in=data['diff'])
            if data['min_meter']:
                qset = qset.filter(meter__gte=data['min_meter'])
            if data['max_meter']:
                qset = qset.filter(meter__lte=data['max_meter'])

            # perform ordering
            if data['order_by']:
                if data['order_by'] == 'title':
                    # do case-insensitive sort
                    order_fields = [Upper('song__title')]
                else: # release_date
                    order_fields = [
                        F('release_date'), Upper('song__title')
                    ]
            else:
                order_fields = [Upper('song__title')]
            order_fields.extend([F('steps_type'), F('difficulty')])
            if data['order_dir'] == 'desc':
                order_fields = [
                    field.desc(nulls_last=True) for field in order_fields
                ]
            else:
                order_fields = [
                    field.asc(nulls_last=True) for field in order_fields
                ]
            qset = qset.order_by(*order_fields)

        else:
            qset = Chart.objects.order_by(Upper('song__title'))
        return qset
    
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        ctx['form'] = ChartSearchForm(self.request.GET)

        ctx['charts'] = ctx['charts'] \
            .select_related('song__pack__category', 'song__banner')

        ctx['page_range'] = ctx['paginator'].get_elided_page_range(
            ctx['page_obj'].number, on_each_side=2, on_ends=1
        )

        return ctx