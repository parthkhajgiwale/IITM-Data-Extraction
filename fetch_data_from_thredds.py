import requests
import re
from bs4 import BeautifulSoup
import xarray as xr
import os

def construct_thredds_url(dataset, frequency, variable):
    """
    Constructs the THREDDS catalog URL based on dataset type (CMIP6 or WAS-44i).
    """
    if dataset.lower() == "cmip6":
        base_url = "https://esg-cccr.tropmet.res.in/thredds/catalog/esg_dataroot6/historical/CMIP6/CMIP/CCCR-IITM/IITM-ESM/historical/r1i1p1f1/{frequency}/{variable}/gn/v20191226/catalog.html"
    elif dataset.lower() == "was-44i":
        base_url = "https://esg-cccr.tropmet.res.in/thredds/catalog/esg_dataroot4/cordex/output/WAS-44i/IITM/CCCma-CanESM2/historical/r1i1p1/IITM-RegCM4-4/v5/{frequency}/{variable}/v20160825/catalog.html"
    else:
        raise ValueError("Invalid dataset. Choose 'CMIP6' or 'WAS-44i'.")

    return base_url.format(frequency=frequency, variable=variable)

def fetch_available_files(url):
    """
    Fetches NetCDF file names from the THREDDS catalog page.
    """
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        print(f"Failed to fetch data from {url}. Status Code:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Extract NetCDF file links
    file_links = []
    for link in soup.find_all("a", href=True):
        if link["href"].endswith(".nc"):  # Only consider NetCDF files
            file_links.append(link["href"])
    
    return file_links

def filter_files_by_duration(files, start_year, end_year):
    """
    Filters NetCDF files based on whether they overlap with the given duration.
    """
    filtered_files = []
    file_urls = {}

    for file in files:
        match = re.search(r"(\d{4})-(\d{4})", file)  # Extract year range
        if match:
            file_start, file_end = int(match.group(1)), int(match.group(2))
            
            if not (file_end < start_year or file_start > end_year):  # Check overlap
                filename = file.split("=")[-1]  
                
                # Construct HTTP URL
                file_server_url = f"https://esg-cccr.tropmet.res.in/thredds/fileServer/{filename}"

                file_urls[filename] = file_server_url
                filtered_files.append(filename)

    return filtered_files, file_urls

def download_file(url, filename):
    """
    Downloads a NetCDF file from the given URL.
    """
    response = requests.get(url, stream=True, verify=False)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Downloaded file: {filename}")
    else:
        print(f"❌ Failed to download {filename}. HTTP Status:", response.status_code)

def merge_and_extract_data(files, file_urls, variable, start_year, end_year):
    """
    Downloads, merges, and extracts data from multiple NetCDF files.
    Displays overall statistics after merging.
    """
    datasets = []
    
    for file in files:
        http_url = file_urls[file]
        local_filename = file.split("/")[-1]
        
        try:
            # Download the file
            print(f"Downloading: {http_url}")
            download_file(http_url, local_filename)

            # Open the file
            dataset = xr.open_dataset(local_filename)
            dataset_filtered = dataset[variable].sel(time=slice(f"{start_year}-01-01", f"{end_year}-12-31"))

            datasets.append(dataset_filtered)

        except Exception as e:
            print(f"❌ Failed to process {file}. Error: {e}")

    # Merge datasets if multiple files exist
    if len(datasets) > 1:
        merged_data = xr.concat(datasets, dim="time")
        print("\n✅ Merged data from multiple files.")
    elif datasets:
        merged_data = datasets[0]  # Single dataset case
    else:
        print("❌ No data extracted.")
        return None

    # Display overall statistics
    print(f"\n📊 **Merged Data Overview**")
    print(f"Time Range: {merged_data.time.values[0]} to {merged_data.time.values[-1]}")
    print(f"Shape: {merged_data.shape}")
    print(f"Mean Value: {merged_data.mean().values:.2f}")
    print(f"Sample Data:\n{merged_data.values[:5]}")  # Show first 5 values

    return merged_data

# Example User Inputs
dataset_type = "CMIP6"  
user_frequency = "Amon"  
user_variable = "uas"  
start_year, end_year = 2008, 2012 

# Step 1: Construct URL
thredds_url = construct_thredds_url(dataset_type, user_frequency, user_variable)
print("Fetching from:", thredds_url)

# Step 2: Fetch Available Files
available_files = fetch_available_files(thredds_url)
if not available_files:
    print("No files found.")
    exit()

# Step 3: Filter Files Based on Duration
filtered_files, file_urls = filter_files_by_duration(available_files, start_year, end_year)
if not filtered_files:
    print("No matching files found for the given time range.")
    exit()

# Step 4: Merge & Extract Data
merged_data = merge_and_extract_data(filtered_files, file_urls, user_variable, start_year, end_year)
