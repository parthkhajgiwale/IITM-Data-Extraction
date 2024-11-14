from django.db import models

class ClimateFile(models.Model):
    variable_name = models.CharField(max_length=50)
    file_path = models.TextField()  # Path to the climate data file
    file_name = models.CharField(max_length=255)  # File name

    class Meta:
        db_table = 'climate_files'  # Explicitly set the table name

    def __str__(self):
        return self.file_name

