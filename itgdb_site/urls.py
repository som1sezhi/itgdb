from django.urls import path

from . import views

app_name = 'itgdb_site'
urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('packs/<int:pk>/', views.PackDetailView.as_view(), name='pack_detail'),
    path('songs/<int:pk>/', views.SongDetailView.as_view(), name='song_detail'),
    path('pack_search/', views.PackSearchView.as_view(), name='pack_search'),
    path('song_search/', views.SongSearchView.as_view(), name='song_search'),
    path('chart_search/', views.ChartSearchView.as_view(), name='chart_search'),
]