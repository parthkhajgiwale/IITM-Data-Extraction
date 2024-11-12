# Example model definition
from django.db import models

class ClimateFile(models.Model):
    variable_name = models.CharField(max_length=50)
    file_path = models.TextField()
    file_name = models.CharField(max_length=255)

    class Meta:
        db_table = 'climate_files'  # explicitly define the correct table name
