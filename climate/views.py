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
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm

logger = logging.getLogger(__name__)
plt.clf()
# Database configuration
DB_CONFIG = settings.DB_CONFIG

def base(request):
    return render(request, 'base.html')
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = form.cleaned_data.get('first_name')
            user.last_name = form.cleaned_data.get('last_name')
            user.save()
            login(request, user)
            messages.success(request, "Registration successful!")
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
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
    models = ['CMIP6', 'WAS-44i']
    return render(request, 'index.html', {'climate_variables': climate_variables, 'models': models})


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

        lons = np.array([coord[1] for coord in coordinates])
        lats = np.array([coord[0] for coord in coordinates])

        # Retrieve file paths
        file_paths = get_file_paths(variable, model)
        if not file_paths:
            logger.error(f"No data available for variable '{variable}' and model '{model}'.")
            return JsonResponse({'error': f"No data available for variable '{variable}' and model '{model}'."}, status=404)

        # Open dataset
        datasets = xr.open_mfdataset(file_paths, combine='by_coords')

        # Validate variable exists in dataset
        if variable not in datasets:
            logger.error(f"Variable '{variable}' not found in the dataset.")
            return JsonResponse({'error': f"Variable '{variable}' not found in the dataset."}, status=400)

        # Time filtering logic
        time_dim = datasets['time']
        if isinstance(time_dim.values[0], cftime.datetime):
            time_dim_values = normalize_cftime_to_gregorian(time_dim.values)
        else:
            time_dim_values = pd.to_datetime(time_dim.values)

        datasets.coords['time'] = time_dim_values

        # Apply time range filter
        start_date_dt = pd.Timestamp(start_date)
        end_date_dt = pd.Timestamp(end_date)
        time_filtered_data = datasets[variable].sel(time=slice(start_date_dt, end_date_dt))

        # Handle regional data selection
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        regional_data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))

        # Get lat and lon grid for the regional data
        lon_values, lat_values = np.meshgrid(regional_data.lon.values, regional_data.lat.values)

        # Check shapes of the grid and data
        print(f"Shape of lon_values: {lon_values.shape}")
        print(f"Shape of lat_values: {lat_values.shape}")
        print(f"Shape of data_values: {regional_data.values.shape}")

        # Select a specific time step (e.g., the first time step)
        data_values = regional_data.values[0, :, :]  # Selecting the first time step for simplicity

        # Ensure lon_values, lat_values, and data_values are the same shape
        if lon_values.shape != lat_values.shape or lon_values.shape != data_values.shape:
            raise ValueError(f"Shape mismatch: lon_values, lat_values, and data_values must have the same shape.")

        # Perform interpolation at the requested coordinates
        interpolated_values = griddata(
            (lon_values.flatten(), lat_values.flatten()),
            data_values.flatten(),
            (lons, lats),
            method='linear'
        )

        # Handle NaN values in the interpolated results
        interpolated_values = np.nan_to_num(interpolated_values, nan=0)

        # Create contour plot
        fig, ax = plt.subplots(figsize=(8, 6), dpi=200, subplot_kw={'projection': ccrs.PlateCarree()})
        ax.set_extent([min_lon, max_lon, min_lat, max_lat], crs=ccrs.PlateCarree())

        # Add features to the map
        ax.add_feature(cfeature.LAND, edgecolor='black')
        ax.add_feature(cfeature.COASTLINE, edgecolor='black')
        ax.add_feature(cfeature.BORDERS, edgecolor='gray', linestyle=':', linewidth=1)
        ax.gridlines(draw_labels=True, linewidth=1, color='gray', linestyle='--')

        # Create contour plot
        contour = ax.contourf(lon_values, lat_values, data_values, 20, cmap='viridis', transform=ccrs.PlateCarree())

        # Add color bar
        cbar = plt.colorbar(contour, ax=ax, orientation='vertical', pad=0.05)
        cbar.set_label(f'Concentration of {variable}', fontsize=12)

        # Title for the plot
        plt.title(f'Spatial Distribution of {variable} ({model})', fontsize=16)

        # Save plot to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)

        # Return the plot as an HTTP response
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
        # Extract request parameters
        coordinates = request.GET.get('coordinates')
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        variable = request.GET.get('variable')
        model = request.GET.get('model')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        # Validate required parameters
        if not variable or not model or not start_date or not end_date:
            return JsonResponse({'error': 'Variable, model, start date, and end date are required.'}, status=400)

        # Retrieve file paths from the database
        file_paths = get_file_paths(variable, model)
        if not file_paths:
            return JsonResponse({'error': f"No data available for the selected parameters: variable='{variable}', model='{model}'."}, status=404)

        # Open dataset
        datasets = xr.open_mfdataset(file_paths, combine='by_coords')

        # Ensure the variable exists in the dataset
        if variable not in datasets.variables:
            return JsonResponse({'error': f"Variable '{variable}' not found in the dataset."}, status=400)

        # Normalize time to Gregorian if cftime objects are used
        if not pd.api.types.is_datetime64_any_dtype(datasets['time']):
            datasets['time'] = normalize_cftime_to_gregorian(datasets['time'].values)

        # Convert start_date and end_date to datetime
        start_date_dt = datetime.strptime(start_date, "%Y-%m")
        end_date_dt = datetime.strptime(end_date, "%Y-%m")

        # Slice the dataset by time
        time_filtered_data = datasets[variable].sel(time=slice(start_date_dt, end_date_dt))

        # Handle point-based selection
        if lat and lon:
            lat, lon = float(lat), float(lon)
            data = time_filtered_data.sel(lat=lat, lon=lon, method="nearest")

        # Handle polygon-based regional average
        elif coordinates:
            coords = [tuple(map(float, coord.split(','))) for coord in coordinates.split(';')]
            min_lat, max_lat = min(c[0] for c in coords), max(c[0] for c in coords)
            min_lon, max_lon = min(c[1] for c in coords), max(c[1] for c in coords)
            regional_data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))
            data = regional_data.mean(dim=["lat", "lon"], skipna=True)

        else:
            return JsonResponse({'error': 'Please provide either lat/lon or region coordinates.'}, status=400)

        # Ensure data is not empty
        if data.size == 0:
            return JsonResponse({'error': 'No data available for the selected time range or spatial coordinates.'}, status=404)

        # Convert to DataFrame and normalize time
        time_series_df = data.to_dataframe().reset_index()
        time_series_df['time'] = pd.to_datetime(time_series_df['time'])
        time_series_df['time'] = time_series_df['time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

        # Return the time series data as JSON
        return JsonResponse(time_series_df.to_dict(orient='records'), safe=False)

    except Exception as e:
        print(f"Error occurred: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def download_csv(request):
    """Generate and return CSV data for download."""
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
            return JsonResponse({'error': 'Variable, model, start date, and end date are required.'}, status=400)

        # Retrieve file paths
        file_paths = get_file_paths(variable, model)
        if not file_paths:
            return JsonResponse({'error': 'No files found for the selected variable and model.'}, status=404)

        # Open dataset and filter by time
        datasets = xr.open_mfdataset(file_paths, combine='by_coords')
        datasets['time'] = normalize_cftime_to_gregorian(datasets['time'].values)
        time_filtered_data = datasets[variable].sel(time=slice(start_date, end_date))

        # Handle data selection (point or region)
        if lat and lon:
            lat, lon = float(lat), float(lon)
            data = time_filtered_data.sel(lat=lat, lon=lon, method="nearest")
        elif coordinates:
            coords = [tuple(map(float, coord.split(','))) for coord in coordinates.split(';')]
            min_lat, max_lat = min(c[0] for c in coords), max(c[0] for c in coords)
            min_lon, max_lon = min(c[1] for c in coords), max(c[1] for c in coords)
            data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))

        # Convert data to a DataFrame
        time_series_df = data.to_dataframe().reset_index()

        # Create CSV response
        csv_data = io.StringIO()
        time_series_df.to_csv(csv_data, index=False)
        csv_data.seek(0)
        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="climate_data.csv"'
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
