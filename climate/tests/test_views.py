import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "climate_project.settings")  # Update with your project’s settings module
django.setup()


from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from unittest.mock import patch, MagicMock
import psycopg2
import re
from climate.views import get_file_paths , normalize_cftime_to_gregorian , send_progress, get_filtered_file_urls

@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('register')
        self.valid_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password1': 'StrongPassword123',
            'password2': 'StrongPassword123',
        }
        self.invalid_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password1': 'password123',  # Weak password
            'password2': 'password321',  # Mismatch
        }




    def test_register_view_post_invalid_data(self):
        response = self.client.post(self.register_url, self.invalid_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='johndoe').exists())
        self.assertEqual(len(mail.outbox), 0)  # No email sent



class GetFilePathsTestCase(TestCase):

    @patch('climate.views.psycopg2.connect')
    def test_get_file_paths_valid(self, mock_connect):
        """Test retrieving file paths for a valid variable and model."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchall.return_value = [
            ('/path/to/file1.nc',),
            ('/path/to/file2.nc',)
        ]
        mock_connect.return_value = mock_conn

        paths = get_file_paths('temperature', 'CMIP6')
        self.assertEqual(paths, ['/path/to/file1.nc', '/path/to/file2.nc'])
        
        mock_cursor.execute.assert_called_once_with(
            "SELECT file_path FROM climate_files WHERE variable_name = %s AND model = %s",
            ('temperature', 'CMIP6')
        )
        mock_conn.close.assert_called_once()

    @patch('climate.views.psycopg2.connect')
    def test_get_file_paths_no_results(self, mock_connect):
        """Test retrieving file paths when no results are found."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchall.return_value = []
        mock_connect.return_value = mock_conn

        paths = get_file_paths('precipitation', 'CMIP6')
        self.assertEqual(paths, [])

        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('climate.views.psycopg2.connect', side_effect=psycopg2.OperationalError("Database connection failed"))
    def test_get_file_paths_db_connection_error(self, mock_connect):
        """Test handling of database connection failure."""
        with self.assertRaises(psycopg2.OperationalError) as context:
            get_file_paths('wind_speed', 'CMIP6')

        self.assertEqual(str(context.exception), "Database connection failed")
        mock_connect.assert_called_once()

    @patch('climate.views.psycopg2.connect')
    def test_get_file_paths_query_failure(self, mock_connect):
        """Test handling of SQL execution failure."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.execute.side_effect = psycopg2.Error("Query failed")
        mock_connect.return_value = mock_conn

        with self.assertRaises(psycopg2.Error) as context:
            get_file_paths('humidity', 'CMIP6')

        self.assertEqual(str(context.exception), "Query failed")
        mock_conn.close.assert_called_once()

import unittest
import pandas as pd
import cftime

class TestNormalizeCftimeToGregorian(unittest.TestCase):

    def test_cftime_conversion(self):
        """Test conversion of cftime.datetime objects to Gregorian format."""
        time_array = [
            cftime.DatetimeGregorian(2023, 5, 10, 12, 30, 45),
            cftime.DatetimeNoLeap(2022, 3, 15, 6, 0, 0)  # Different cftime calendar
        ]
        result = normalize_cftime_to_gregorian(time_array)

        expected = pd.to_datetime(["2023-05-10 12:30:45", "2022-03-15 06:00:00"])
        pd.testing.assert_index_equal(result, expected)

    def test_standard_datetime_conversion(self):
        """Test conversion of standard datetime objects."""
        time_array = [
            pd.Timestamp("2021-07-19 14:05:30"),
            "2020-12-31 23:59:59"
        ]
        result = normalize_cftime_to_gregorian(time_array)

        expected = pd.to_datetime(["2021-07-19 14:05:30", "2020-12-31 23:59:59"])
        pd.testing.assert_index_equal(result, expected)

    def test_mixed_inputs(self):
        """Test conversion of mixed cftime, datetime, and string formats."""
        time_array = [
            cftime.DatetimeProlepticGregorian(2019, 11, 5, 8, 15, 0),
            pd.Timestamp("2018-06-20 10:45:30"),
            "2017-01-01 00:00:00"
        ]
        result = normalize_cftime_to_gregorian(time_array)

        expected = pd.to_datetime(["2019-11-05 08:15:00", "2018-06-20 10:45:30", "2017-01-01 00:00:00"])
        pd.testing.assert_index_equal(result, expected)

    def test_empty_input(self):
        """Test handling of an empty input list."""
        result = normalize_cftime_to_gregorian([])
        expected = pd.to_datetime([])
        pd.testing.assert_index_equal(result, expected)

    def test_invalid_input(self):
        """Test handling of completely invalid input values."""
        with self.assertRaises(Exception):  # Expecting ValueError or TypeError
            normalize_cftime_to_gregorian(["invalid_date", 12345, None])

from django.test import TestCase, Client
from django.core.cache import cache
from django.urls import reverse

class ProgressTestCase(TestCase):

    def setUp(self):
        """Setup runs before every test to ensure a clean cache."""
        cache.clear()
        self.client = Client()

    def test_send_progress(self):
        """Test that progress is correctly stored in cache."""
        send_progress(50)
        self.assertEqual(cache.get("download_progress"), 50)

    @override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
    def test_get_progress_with_stored_value(self):
        """Test retrieval of stored progress from cache."""
        cache.set("download_progress", 75, timeout=60)
        response = self.client.get(reverse("get_progress"))  # Ensure URL is correctly mapped
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"progress": 75})

    @override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
    def test_get_progress_without_stored_value(self):
        """Test retrieval when no progress is set."""
        response = self.client.get(reverse("get_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"progress": "No progress yet"})



class GetFilteredFileUrlsTestCase(TestCase):

    @patch("climate.views.psycopg2.connect")  # Mock the database connection
    def test_get_filtered_file_urls_success(self, mock_connect):
        """Test fetching file paths with valid inputs."""

        # Mock database cursor and fetchall return value
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("file1.nc",), ("file2.nc",)]  # Simulated file paths

        variable = "temperature"
        model = "CMIP6"
        start_date = "2000-01-01"
        end_date = "2020-12-31"

        result = get_filtered_file_urls(variable, model, start_date, end_date)

        self.assertEqual(result, ["file1.nc", "file2.nc"])

        # Normalize whitespace in the SQL query before assertion
        def normalize_whitespace(query):
            return re.sub(r'\s+', ' ', query).strip()

        expected_query = """
        SELECT file_path FROM climate_files
        WHERE variable_name = %s AND model = %s
        AND start_year <= %s AND end_year >= %s
        """

        mock_cursor.execute.assert_called_once_with(
            normalize_whitespace(expected_query),
            (variable, model, 2000, 2020),  # Fix parameter order
        )

    @patch("climate.views.psycopg2.connect")
    def test_get_filtered_file_urls_no_results(self, mock_connect):
        """Test fetching file paths when no matching records are found."""

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []  # No matching results

        variable = "rainfall"
        model = "CMIP5"
        start_date = "1990-01-01"
        end_date = "1995-12-31"

        result = get_filtered_file_urls(variable, model, start_date, end_date)

        self.assertEqual(result, [])  # Should return an empty list

    @patch("climate.views.psycopg2.connect")
    def test_get_filtered_file_urls_db_exception(self, mock_connect):
        """Test handling of database connection failure."""

        mock_connect.side_effect = Exception("Database connection error")

        with self.assertRaises(Exception) as context:
            get_filtered_file_urls("co2", "CMIP6", "2010-01-01", "2020-12-31")

        self.assertIn("Database connection error", str(context.exception))


if __name__ == "__main__":
    unittest.main()