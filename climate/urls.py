from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('get_timeseries/', views.get_timeseries, name='get_timeseries'),
    path('download_csv/', views.download_csv, name='download_csv'),
]
