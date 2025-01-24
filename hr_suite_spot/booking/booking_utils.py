# Utility functions for booking functionality
# Import MultiDict for form input handling
from werkzeug.datastructures import MultiDict
import re
from datetime import datetime, tzinfo, timezone, timedelta
from .error_utils import TimeValidationError




def validate_availability_input_format(input: MultiDict) -> bool:
    """Fomat IAF:
    Monday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Tuesday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Wednesday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Thursday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Friday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Saturday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],
    Sunday: ['YEAR-MM-DD HH:MM:SS', 'YEAR-MM-DD HH:MM:SS'],

    Sanitize input.

    In past time checks done in other util, this is only for format.

    Pattern matching done with REGEX.
    """
    pattern = re.compile('^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\s([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$') # Pattern match for full ISO format without timezone

    # Should be two values for each key
    for value in input.values():
        # Only test if the input isn't empty for given day of week
        # Empty string is default value
        if value == '':
            continue
        # Test for fullmatch against regex pattern
        if not pattern.fullmatch(value):
            # If any inputs fail end loop
            return False
    return True

def convert_to_iso_with_tz(input: MultiDict) -> dict:
    """
    Convert's the availability input into ISO-format in UTC and returns it as a regular dictionary to be used for Jsonify. 
    Performs all non-format time validations.

    Input of availability assumed to be in PST

    Raises:
        TimeValidationError: If validation parameters not met. See TimeValidationError docs.

    Output format:
    {'Monday': ['2025-02-01T01:01:00-08:00', '2025-02-03T01:01:00-08:00']}
    """
    availability_in_iso = {}
    for key in input.keys():
        start, end = input.getlist(key)
        # If no input for a field, skip to prevent ValueError in processing below
        if start == '' or end == '':
            continue
        # Convert to datetime objects to handle time conversions, starts off as naive objects but convert to aware

        # Convert str format into datetime objects
        format_str = "%Y-%m-%d %H:%M:%S"
        start = datetime.strptime(start, format_str)
        end = datetime.strptime(end, format_str)

        tz = timezone(timedelta(hours=-8)) # Pre-set for PST

        # Add in time-zone
        start = start.replace(tzinfo=tz)
        end = end.replace(tzinfo=tz)

        # Perform past check
        now = datetime.now(tz=tz) # Set timezone for now to ensure stable deployment in prod environment
        if start < now or end < now: raise TimeValidationError(message="Time cannot be in past") # Remember to pass off message in front end
        if end <= start: raise TimeValidationError(message="End of time period cannot be less than or equal to the start")
        # Perform month and day range checks
        # Do not assume amount people can book into future to keep flexibility in appication open
        month_set = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}
        if start.month not in month_set: raise TimeValidationError(message="Not a valid month")
        if end.month not in month_set: raise TimeValidationError(message="Not a valid month")

        start_iso = start.isoformat()
        end_iso = end.isoformat()
        # TODo...
        #  2. Time input matched input format but not valid ISO ranges
        # 3. Leap year is not handled if it is a valid leap year
        # 4. The input day range for given month does not meet valid range

        # Use final ISO-formatted with timezone as return values for JSON API pass
        availability_in_iso[key] = [start_iso, end_iso]
    return availability_in_iso



    