import requests
import re
import psycopg2
from bs4 import BeautifulSoup

# Database connection details
DB_NAME = "climate_data"
DB_USER = "postgres"
DB_PASSWORD = "your_postgres_password"
DB_HOST = "localhost"
DB_PORT = "5432"

DATASET_URLS = {
    "cmip6": "https://esg-cccr.tropmet.res.in/thredds/catalog/esg_dataroot6/historical/CMIP6/CMIP/CCCR-IITM/IITM-ESM/historical/r1i1p1f1/{frequency}/{variable}/gn/v20191226/catalog.html",
    "was-44i": "https://esg-cccr.tropmet.res.in/thredds/catalog/esg_dataroot4/cordex/output/WAS-44i/IITM/CCCma-CanESM2/historical/r1i1p1/IITM-RegCM4-4/v5/{frequency}/{variable}/v20160825/catalog.html"
}

# PostgreSQL connection
def connect_db():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

# Create table if not exists
def create_table():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS climate_files (
            id SERIAL PRIMARY KEY,
            variable_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            model TEXT NOT NULL,
            start_year INT NOT NULL,
            end_year INT NOT NULL,
            frequency TEXT NOT NULL
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# Construct THREDDS URL
def construct_thredds_url(dataset, frequency, variable):
    if dataset.lower() not in DATASET_URLS:
        raise ValueError("Invalid dataset. Choose 'cmip6' or 'was-44i'.")
    return DATASET_URLS[dataset.lower()].format(frequency=frequency, variable=variable)

# Fetch available NetCDF files
def fetch_available_files(url):
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        print(f"❌ Failed to fetch data from {url}. Status Code:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    return [link["href"] for link in soup.find_all("a", href=True) if link["href"].endswith(".nc")]

# Extract metadata
def extract_file_metadata(files, dataset, frequency, variable):
    extracted_data = []
    for file in files:
        match = re.search(r"_(\d{4})\d{2}-(\d{4})\d{2}\.nc", file)  # ✅ Corrected regex
        if not match:
            print(f"⚠️ Could not extract years from {file}")
            continue

        start_year, end_year = int(match.group(1)), int(match.group(2))
        filename = file.split("=")[-1] 
        file_path = f"https://esg-cccr.tropmet.res.in/thredds/fileServer/{filename}"

        extracted_data.append({
            "variable_name": variable,
            "file_path": file_path,
            "file_name": file.split("/")[-1],
            "model": dataset.upper(),
            "start_year": start_year,
            "end_year": end_year,
            "frequency": frequency
        })
    return extracted_data

# Insert into PostgreSQL
def insert_into_db(data):
    conn = connect_db()
    cur = conn.cursor()
    
    for record in data:
        cur.execute("""
            INSERT INTO climate_files (variable_name, file_path, file_name, model, start_year, end_year, frequency)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (record["variable_name"], record["file_path"], record["file_name"], 
              record["model"], record["start_year"], record["end_year"], record["frequency"]))
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Data successfully inserted into PostgreSQL.")

# Main execution
def main(dataset, frequency, variable):
    create_table()
    
    thredds_url = construct_thredds_url(dataset, frequency, variable)
    print(f"Fetching from: {thredds_url}")

    files = fetch_available_files(thredds_url)
    if not files:
        print("❌ No files found.")
        return

    extracted_data = extract_file_metadata(files, dataset, frequency, variable)
    insert_into_db(extracted_data)

    print("✅ Process completed.")

# Example usage
if __name__ == "__main__":
    dataset_type = "cmip6"  # Change to "was-44i" if needed
    user_frequency = "Amon"  # Change as needed
    user_variable = "tas"  # Change as needed

    main(dataset_type, user_frequency, user_variable)