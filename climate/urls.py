from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    path('', views.base, name='base'),
    path('home/', views.home, name='home'),
    path('get_timeseries/', views.get_timeseries, name='get_timeseries'),
    path('download_csv/', views.download_csv, name='download_csv'),
    path('get_spatial_plot', views.get_spatial_plot, name='get_spatial_plot'),
    path('register/', views.register_view, name='register'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
]
