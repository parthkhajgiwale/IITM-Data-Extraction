import matplotlib

matplotlib.use('Agg')  # Use the 'Agg' backend for headless environments
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import xarray as xr
import pandas as pd
import cftime
from sklearn.preprocessing import StandardScaler
from scipy.interpolate import griddata
import io
from datetime import datetime
import psycopg2
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm
import tempfile
import requests
import os
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm
from django.core.mail import send_mail

logger = logging.getLogger(__name__)
plt.clf()
# Database configuration
DB_CONFIG = settings.DB_CONFIG


def base(request):
    return render(request, 'home.html')

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.first_name = form.cleaned_data.get('first_name')
                user.last_name = form.cleaned_data.get('last_name')
                password = form.cleaned_data.get('password1')
                user.set_password(password)
                user.save()
                login(request, user)
                messages.success(request, "Registration successful!")

                subject = "Welcome to Our Platform!"
                message = f"Hello {user.first_name},\n\nYour account has been created successfully.\n\nUsername: {user.username}\nPassword: {password}\n\nPlease change your password after logging in.\n\nBest regards,\nTeam"
                from_email = settings.DEFAULT_FROM_EMAIL
                recipient_list = [user.email]

                send_mail(subject, message, from_email, recipient_list, fail_silently=False)

                return redirect('home')
            except Exception as e:
                logger.error(f"Error during user registration: {str(e)}")
                messages.error(request, "An error occurred during registration. Please try again.")
        else:
            logger.warning(f"Form validation errors: {form.errors}")
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegisterForm()
    return render(request, 'loginregister.html', {'form': form})

def faq_view(request):
    return render(request, 'faq.html')  # or whatever template you use
def contact_view(request):
    return render(request, 'contact.html')  # or whatever template you use
def forgot_view(request):
    return render(request, 'forgot.html')  # or whatever template you use



@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('login')


def get_file_paths(variable, model):
    """Retrieve file paths for the given climate variable and model."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "SELECT file_path FROM climate_files WHERE variable_name = %s AND model = %s"
        cursor.execute(query, (variable, model))
        paths = [row[0] for row in cursor.fetchall()]
        return paths
    except Exception as e:
        print(f"Error fetching file paths: {e}")
        raise
    finally:
        if conn:
            conn.close()


def normalize_cftime_to_gregorian(time_array):
    """Convert cftime objects to Gregorian calendar."""
    converted_times = []
    for t in time_array:
        if isinstance(t, cftime.datetime):
            converted_times.append(t.strftime("%Y-%m-%d %H:%M:%S"))  # Format to string first
        else:
            converted_times.append(pd.Timestamp(t))  # Directly use Pandas for non-cftime objects
    return pd.to_datetime(converted_times)


@login_required
def home(request):
    """Render the homepage with variable and model options."""
    climate_variables = ['vas', 'tas', 'pr']
    models = ['CMIP6', 'WAS-44I']
    return render(request, 'tool.html', {'climate_variables': climate_variables, 'models': models})


def get_spatial_plot(request):
    try:
        # Extract parameters from the request
        variable = request.GET.get('variable')
        model = request.GET.get('model')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        coordinates_str = request.GET.get('coordinates')

        # Validate required parameters
        if not all([variable, model, start_date, end_date, coordinates_str]):
            logger.error("Missing required parameters.")
            return JsonResponse({"error": "Missing required parameters"}, status=400)

        # Parse coordinates
        coordinates = [tuple(map(float, coord.split(','))) for coord in coordinates_str.split(';')]
        if not coordinates:
            logger.error("No valid coordinates provided.")
            return JsonResponse({"error": "No valid coordinates provided."}, status=400)

        # Get required file URLs based on time range
        file_urls = get_filtered_file_urls(variable, model, start_date, end_date)
        if not file_urls:
            logger.error("No files found for the selected variable, model, and time range.")
            return JsonResponse({'error': 'No files found for the selected variable, model, and time range.'},
                                status=400)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_files = []

            # Download NetCDF files
            for url in file_urls:
                temp_path = os.path.join(temp_dir, os.path.basename(url))
                response = requests.get(url, stream=True, verify=False)

                if response.status_code == 200:
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    temp_files.append(temp_path)
                else:
                    return JsonResponse({'error': f'Failed to download {url}'}, status=400)

            # Open dataset while preserving spatial structure
            with xr.open_mfdataset(temp_files, combine='by_coords', decode_cf=True, engine="netcdf4") as datasets:
                # Normalize time format
                datasets['time'] = normalize_cftime_to_gregorian(datasets['time'].values)

                # Select time range
                time_filtered_data = datasets[variable].sel(time=slice(start_date, end_date))

                # Extract spatial region
                lons = np.array([coord[1] for coord in coordinates])
                lats = np.array([coord[0] for coord in coordinates])
                min_lat, max_lat = min(lats), max(lats)
                min_lon, max_lon = min(lons), max(lons)

                regional_data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))

                # Get lat and lon grid
                lon_values, lat_values = np.meshgrid(regional_data.lon.values, regional_data.lat.values)

                # Select a single time step (first time step for now)
                data_values = regional_data.values[0, :, :]

                # Ensure shape consistency
                if lon_values.shape != lat_values.shape or lon_values.shape != data_values.shape:
                    raise ValueError(f"Shape mismatch: lon_values, lat_values, and data_values must have the same shape.")

                # Perform interpolation at requested coordinates
                interpolated_values = griddata(
                    (lon_values.flatten(), lat_values.flatten()),
                    data_values.flatten(),
                    (lons, lats),
                    method='linear'
                )

                # Handle NaN values in interpolation
                interpolated_values = np.nan_to_num(interpolated_values, nan=0)

                # Create spatial plot
                fig, ax = plt.subplots(figsize=(8, 6), dpi=200, subplot_kw={'projection': ccrs.PlateCarree()})
                ax.set_extent([min_lon, max_lon, min_lat, max_lat], crs=ccrs.PlateCarree())

                # Add map features
                ax.add_feature(cfeature.LAND, edgecolor='black')
                ax.add_feature(cfeature.COASTLINE, edgecolor='black')
                ax.add_feature(cfeature.BORDERS, edgecolor='gray', linestyle=':', linewidth=1)
                ax.gridlines(draw_labels=True, linewidth=1, color='gray', linestyle='--')

                # Contour plot
                contour = ax.contourf(lon_values, lat_values, data_values, 20, cmap='viridis', transform=ccrs.PlateCarree())

                # Add color bar
                cbar = plt.colorbar(contour, ax=ax, orientation='vertical', pad=0.05)
                cbar.set_label(f'Concentration of {variable}', fontsize=12)

                # Title
                plt.title(f'Spatial Distribution of {variable} ({model})', fontsize=16)

                # Save plot to buffer
                buffer = io.BytesIO()
                plt.savefig(buffer, format='png', bbox_inches='tight')
                buffer.seek(0)

            return HttpResponse(buffer, content_type='image/png')

    except ValueError as ve:
        logger.error(f"ValueError: {ve}")
        return JsonResponse({"error": str(ve)}, status=400)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


def get_timeseries(request):
    """Fetch and return time-series data as JSON."""
    try:
        logger.info("get_timeseries called")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request GET params: {request.GET}")

        # Extract data using common function
        time_series_df, error = extract_time_series_data(request)
        logger.info(f"extract_time_series_data returned error: {error}")
        logger.info(f"extract_time_series_data returned df: {time_series_df.head() if time_series_df is not None else 'None'}")

        if error:
            logger.error(f"Returning error response: {error}")
            return JsonResponse(error, status=400 if 'error' in error else 500)

        # Convert DataFrame time column to formatted string
        time_series_df['time'] = pd.to_datetime(time_series_df['time']).dt.strftime('%Y-%m-%dT%H:%M:%S')
        logger.info(f"Formatted time column: {time_series_df['time'].head()}")

        # Return the time series data as JSON
        result = time_series_df.to_dict(orient='records')
        logger.info(f"Returning JSON response with {len(result)} records")
        return JsonResponse(result, safe=False)

    except Exception as e:
        logger.exception(f"Error occurred in get_timeseries: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def download_csv(request):
    """Fetch required NetCDF files, extract time-series data, and return as CSV."""
    try:
        # Extract data using common function
        time_series_df, error = extract_time_series_data(request)
        if error:
            return JsonResponse(error, status=500)

        # Create CSV response
        csv_data = io.StringIO()
        time_series_df.to_csv(csv_data, index=False)
        csv_data.seek(0)

        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="climate_data.csv"'
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def extract_time_series_data(request):
    """
    Extracts parameters from request, downloads required NetCDF files,
    processes time-series data, and returns a DataFrame.
    """
    try:
        # Extract request parameters
        coordinates = request.GET.get('coordinates')
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        variable = request.GET.get('variable')
        model = request.GET.get('model')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        # Validate input
        if not variable or not model or not start_date or not end_date:
            return None, {'error': 'Variable, model, start date, and end date are required.'}

        # Get required file URLs based on time range
        file_urls = get_filtered_file_urls(variable, model, start_date, end_date)
        if not file_urls:
            return None, {'error': 'No files found for the selected variable, model, and time range.'}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_files = []

            # Download required NetCDF files
            for url in file_urls:
                temp_path = os.path.join(temp_dir, os.path.basename(url))
                response = requests.get(url, stream=True, verify=False)

                if response.status_code == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress_percent = int((downloaded / total_size) * 100)
                            
                            send_progress(f"Downloading {os.path.basename(url)}: {progress_percent}%")
                    temp_files.append(temp_path)
                    
                else:
                    send_progress(f"Failed to download {url}")
                    return None, {'error': f'Failed to download {url}'}
            try:
                with xr.open_mfdataset(temp_files, combine='by_coords', decode_cf=True, engine="netcdf4") as datasets:
                    # Normalize time format
                    datasets['time'] = normalize_cftime_to_gregorian(datasets['time'].values)
                    time_filtered_data = datasets[variable].sel(time=slice(start_date, end_date))

                    # Handle data selection (point or region)
                    if lat and lon:
                        lat, lon = float(lat), float(lon)
                        data = time_filtered_data.sel(lat=lat, lon=lon, method="nearest")
                    elif coordinates:
                        coords = [tuple(map(float, coord.split(','))) for coord in coordinates.split(';') if coord]
                        if not coords:
                            return None, {'error': 'No valid coordinates provided.'}
                        min_lat, max_lat = min(c[0] for c in coords), max(c[0] for c in coords)
                        min_lon, max_lon = min(c[1] for c in coords), max(c[1] for c in coords)
                        data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon)).mean(
                            dim=["lat", "lon"])
                    else:
                        return None, {'error': 'No coordinates or lat/lon provided.'}

                    # Convert data to DataFrame
                    time_series_df = data.to_dataframe().reset_index()
            except Exception as e:
                return None, {'error': str(e)}

        return time_series_df, None  # Return DataFrame, no error

    except Exception as e:
        return None, {'error': str(e)}

from django.shortcuts import render
from .models import ClimateFile

def climate_files_view(request, model_type):
    # Filter records by model type
    files = ClimateFile.objects.filter(model=model_type)

    # Get distinct variable names for sidebar
    all_variables = ClimateFile.objects.values_list('variable_name', flat=True).distinct()

    # Apply filter if a variable is selected
    selected_vars = request.GET.getlist('variable')
    if selected_vars:
        files = files.filter(variable_name__in=selected_vars)

    context = {
        'climate_files': files,
        'all_variables': all_variables,
        'selected_vars': selected_vars,
        'model_type': model_type,
    }
    return render(request, 'climate_files_table.html', context)

def get_filtered_file_urls(variable, model, start_date, end_date):
    """
    Fetch only URLs that match the required variable, model, and time range.
    """
    start_year = int(start_date.split('-')[0])
    end_year = int(end_date.split('-')[0])
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """
        SELECT file_path FROM climate_files
        WHERE variable_name = %s AND model = %s
        AND start_year <= %s AND end_year >= %s
        """
        params = (variable, model, end_year, start_year)
        cursor.execute(query, params)
        paths = [row[0] for row in cursor.fetchall()]
        return paths
    except Exception as e:
        print(f"Error fetching file paths: {e}")
        raise
    finally:
        if conn:
            conn.close()


from django.core.cache import cache

def send_progress(progress):
    cache.set("download_progress", progress, timeout=60)  # Store progress for 60 seconds

from django.http import JsonResponse

def get_progress(request):
    progress = cache.get("download_progress", "No progress yet")
    return JsonResponse({"progress": progress})

def forget_password_view(request):
    return render(request, 'forget.html')