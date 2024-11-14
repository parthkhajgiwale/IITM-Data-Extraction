from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import xarray as xr
import pandas as pd
import cftime
import io
from datetime import datetime
import psycopg2
from django.conf import settings

# Database configuration
DB_CONFIG = settings.DB_CONFIG


def get_file_paths(variable_name):
    """Retrieve file paths for the given climate variable."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT file_path FROM climate_files WHERE variable_name = %s", (variable_name,))
    paths = [row[0] for row in cursor.fetchall()]
    conn.close()
    return paths


climate_variables = ['vas', 'tas', 'pr']


def home(request):
    return render(request, 'index.html', {'climate_variables': climate_variables})


def convert_cftime_to_datetime(index):
    """Convert cftime to datetime, handling custom calendars."""
    if isinstance(index[0], cftime.DatetimeNoLeap):
        return pd.to_datetime([pd.Timestamp(i.strftime("%Y-%m-%d")) for i in index])
    return index


def get_timeseries(request):
    try:
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        variable_name = request.GET.get('variable')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        coordinates = request.GET.get('coordinates')

        if not variable_name or not start_date or not end_date:
            return JsonResponse({'error': 'Variable, start date, and end date are required.'}, status=400)

        file_paths = get_file_paths(variable_name)
        if not file_paths:
            return JsonResponse({'error': 'No files found for the selected variable.'}, status=404)

        datasets = xr.open_mfdataset(file_paths, combine='by_coords')
        start_date = datetime.strptime(start_date, "%Y-%m")
        end_date = datetime.strptime(end_date, "%Y-%m")
        start_cftime = cftime.DatetimeNoLeap(start_date.year, start_date.month, 1)
        end_cftime = cftime.DatetimeNoLeap(end_date.year, end_date.month, 1)

        time_filtered_data = datasets[variable_name].sel(time=slice(start_cftime, end_cftime))

        if lat and lon:
            data = time_filtered_data.sel(lat=float(lat), lon=float(lon), method="nearest")
        elif coordinates:
            coords = [tuple(map(float, coord.split(','))) for coord in coordinates.split(';')]
            min_lat = min(coord[0] for coord in coords)
            max_lat = max(coord[0] for coord in coords)
            min_lon = min(coord[1] for coord in coords)
            max_lon = max(coord[1] for coord in coords)
            data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))

        time_series_df = data.to_dataframe().reset_index()
        time_series_df['time'] = convert_cftime_to_datetime(time_series_df['time'])
        time_series_df['time'] = time_series_df['time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

        return JsonResponse(time_series_df.to_dict(orient='records'), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def download_csv(request):
    try:
        lat = request.GET.get('lat')
        lon = request.GET.get('lon')
        variable_name = request.GET.get('variable')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        coordinates = request.GET.get('coordinates')

        if not variable_name or not start_date or not end_date:
            return JsonResponse({'error': 'Variable, start date, and end date are required.'}, status=400)

        file_paths = get_file_paths(variable_name)
        if not file_paths:
            return JsonResponse({'error': 'No files found for the selected variable.'}, status=404)

        datasets = xr.open_mfdataset(file_paths, combine='by_coords')
        start_date = datetime.strptime(start_date, "%Y-%m")
        end_date = datetime.strptime(end_date, "%Y-%m")
        start_cftime = cftime.DatetimeNoLeap(start_date.year, start_date.month, 1)
        end_cftime = cftime.DatetimeNoLeap(end_date.year, end_date.month, 1)

        time_filtered_data = datasets[variable_name].sel(time=slice(start_cftime, end_cftime))

        if lat and lon:
            data = time_filtered_data.sel(lat=float(lat), lon=float(lon), method="nearest")
        elif coordinates:
            coords = [tuple(map(float, coord.split(','))) for coord in coordinates.split(';')]
            min_lat = min(coord[0] for coord in coords)
            max_lat = max(coord[0] for coord in coords)
            min_lon = min(coord[1] for coord in coords)
            max_lon = max(coord[1] for coord in coords)
            data = time_filtered_data.sel(lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon))

        time_series_df = data.to_dataframe().reset_index()
        time_series_df['time'] = convert_cftime_to_datetime(time_series_df['time'])
        time_series_df['time'] = time_series_df['time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

        csv_data = io.StringIO()
        time_series_df.to_csv(csv_data, index=False)
        csv_data.seek(0)

        response = HttpResponse(csv_data, content_type="text/csv")
        response['Content-Disposition'] = 'attachment; filename="climate_data.csv"'
        return response
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
