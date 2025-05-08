from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views
from .views import climate_files_view
from django.contrib.auth import views as auth_views


urlpatterns = [
    path('', views.base, name='base'),
    path('home/', views.home, name='home'),
    path('get_timeseries/', views.get_timeseries, name='get_timeseries'),
    path('download_csv/', views.download_csv, name='download_csv'),
    path('get_spatial_plot', views.get_spatial_plot, name='get_spatial_plot'),
    path('register/', views.register_view, name='register'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset_done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path("get_progress/", views.get_progress, name="get_progress"),
    path('forget/', views.forget_password_view, name='forget_password'),
    path('climate-files/<str:model_type>/', climate_files_view, name='climate_files'),

]
