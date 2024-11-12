from django.shortcuts import render

def home(request):
    climate_variables = ['vas', 'tas', 'pr']
    return render(request, 'climate/index.html', {'climate_variables': climate_variables})

import xarray as xr
import pandas as pd
from django.http import JsonResponse
from .models import ClimateFile
import cftime

def convert_cftime_to_datetime(index):
    if isinstance(index[0], cftime.DatetimeNoLeap):
        return pd.to_datetime([pd.Timestamp(i.strftime("%Y-%m-%d")) for i in index])
    return index

def get_timeseries(request):
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
        variable_name = request.GET.get('variable')
        files = ClimateFile.objects.filter(variable_name=variable_name)
        file_paths = [file.file_path for file in files]

        if not file_paths:
            return JsonResponse({'error': 'No files found for the selected variable.'}, status=404)

        datasets = xr.open_mfdataset(file_paths, combine='by_coords')
        filtered_data = datasets[variable_name].sel(lat=lat, lon=lon, method="nearest")

        time_series_df = filtered_data.to_dataframe().reset_index()
        time_series_df['time'] = convert_cftime_to_datetime(time_series_df['time'])
        time_series_df['time'] = time_series_df['time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

        return JsonResponse(time_series_df.to_dict(orient='records'), safe=False)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

from django.http import HttpResponse
import io

def download_csv(request):
    lat = float(request.GET.get('lat'))
    lon = float(request.GET.get('lon'))
    variable_name = request.GET.get('variable')

    files = ClimateFile.objects.filter(variable_name=variable_name)
    file_paths = [file.file_path for file in files]

    datasets = xr.open_mfdataset(file_paths, combine='by_coords')
    filtered_data = datasets[variable_name].sel(lat=lat, lon=lon, method="nearest")

    time_series_df = filtered_data.to_dataframe().reset_index()
    time_series_df['date'] = time_series_df['time'].apply(lambda x: f"{x.year}-{x.month:02d}")
    time_series_df = time_series_df.drop(columns=['time'])

    csv_data = io.StringIO()
    time_series_df.to_csv(csv_data, index=False)
    csv_data.seek(0)

    response = HttpResponse(csv_data.getvalue(), content_type="text/csv")
    response['Content-Disposition'] = 'attachment; filename="monthly_data.csv"'
    return response
