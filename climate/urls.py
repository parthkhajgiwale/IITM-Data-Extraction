from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('get_timeseries/', views.get_timeseries, name='get_timeseries'),
    path('download_csv/', views.download_csv, name='download_csv'),
    path('get_spatial_plot', views.get_spatial_plot, name='get_spatial_plot')
]
