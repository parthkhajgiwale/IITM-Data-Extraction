import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for web server

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
import pandas as pd
import cftime
import io
from datetime import datetime
import psycopg2
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse

# Database configuration
DB_CONFIG = settings.DB_CONFIG

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

def home(request):
    """Render the homepage with variable and model options."""
    climate_variables = ['vas', 'tas', 'pr']
    models = ['CMIP6', 'WAS-44i']
    return render(request, 'index.html', {'climate_variables': climate_variables, 'models': models})


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
