import os
import shutil
import psycopg2
from psycopg2 import sql

def create_directory_structure_and_move_file(file_name, base_directory):
    # Split the file name into components
    file_parts = file_name.split('_')
    climate_variable = file_parts[0]  # Assuming the variable is the first part of the filename
    model = "CMIP6" if file_parts[1] != "WAS-44i" else None  # Check for 'WAS-44i'

    # Create the directory path using all parts except the last one
    directory_path = os.path.join(base_directory, *file_parts[:-1])
    
    # Create the last directory (e.g., 196101-197012 or 197101-198012)
    last_part = file_parts[-1].rsplit('.', 1)[0]
    full_directory_path = os.path.join(directory_path, last_part)
    os.makedirs(full_directory_path, exist_ok=True)
    
    # Define the source file path
    source_file_path = os.path.join(base_directory, file_name)
    destination_file_path = os.path.join(full_directory_path, file_name)
    
    # Move the file to the new directory structure
    try:
        shutil.move(source_file_path, destination_file_path)
        print(f"File moved to: {destination_file_path}")
        # Log the file details to the PostgreSQL database
        log_file_to_database(climate_variable, destination_file_path, file_name, model)
    except FileNotFoundError:
        print(f"File not found: {source_file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")

def log_file_to_database(variable_name, file_path, file_name, model):
    # Database configuration
    DB_CONFIG = {
        'host': 'localhost',
        'database': 'climate_data',
        'user': 'postgres',  # Replace with your user or 'postgres'
        'password': 'password'  # Replace with your password
    }

    # Connect to the PostgreSQL database and insert the file data
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Insert query with optional model column
        insert_query = sql.SQL("""
            INSERT INTO climate_files (variable_name, file_path, file_name, model)
            VALUES (%s, %s, %s, %s)
        """)
        cursor.execute(insert_query, (variable_name, file_path, file_name, model))
        conn.commit()
        print(f"Logged file '{file_name}' to database with model='{model}'.")
    except psycopg2.Error as e:
        print(f"Database error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Example usage
if __name__ == "__main__":
    base_directory = r"C:\Users\parth\Downloads"  # Base directory for files

    # List of files to be processed
    files_to_process = [
        "tas_Amon_IITM-ESM_historical_r1i1p1f1_gn_201001-201412.nc"
    ]

    # Process each file
    for file_name in files_to_process:
        create_directory_structure_and_move_file(file_name, base_directory)
