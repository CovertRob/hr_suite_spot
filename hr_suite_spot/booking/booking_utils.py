# Utility functions for booking functionality
# Import MultiDict for form input handling
from werkzeug.datastructures import MultiDict
import re
from datetime import datetime, timedelta
from .error_utils import TimeValidationError
from pprint import pprint
from zoneinfo import ZoneInfo

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

    Time checks done in other util, this is only for format.

    Pattern matching done with REGEX.
    """
    pattern = re.compile('^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\s([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$') # Pattern match for full ISO format without timezone

    # Should be two values for each key
    for value in input.values():
        # Only test if the input isn't empty for given day of week
        # Empty string is default value
        # Skip over the boolean inputs for re-occuring submissions
        boolean = ['true', 'false']
        if value == '' or value in boolean:
            continue
        # Test for fullmatch against regex pattern
        if not pattern.fullmatch(value):
            # If any inputs fail end loop
            return False
    return True

def convert_to_iso_with_tz(input: MultiDict, timezone: str) -> MultiDict:
    """
    Takes the input of availability period data already in ISO format and performs time and date validation checks and then adds in timezone info.
    Performs all non-format time validations.

    Input of availability assumed to be in PST. Current implementation is hard coded for -8 UTC.

    Raises:
        TimeValidationError: If validation parameters not met. See TimeValidationError docs.

    Note: ISO format for time states including the 'T' to separate the date and time is optional. User input does not include the T. Output will include the T due to functionality of Python datetime module isoformat() function outputs.

    Output format:
        Note: for re-occurring times there will be multiple pairs, thus the MultiDict return type.
    {'Monday': ['2025-02-01T01:01:00-08:00', '2025-02-03T01:01:00-08:00']}
    """
    availability_in_iso = MultiDict()
    for key in input.keys():
        # Removed empty value check here since it's done in the generate_availability function now prior.
        for days in input.getlist(key):
            # Access first element since getlist() returns the list inside a list
            start, end = days
            # Convert to datetime objects to handle time conversions, starts off as naive objects but convert to aware

            # Convert str format into datetime objects
            format_str = "%Y-%m-%d %H:%M:%S"
            # Have to remove the iso-standard 'T' since Python datetime module automatically  puts it in there. The standard has the 'T' as optional.
            start = datetime.strptime(start.replace('T', ' '), format_str)
            end = datetime.strptime(end.replace('T', ' '), format_str)

            # tz = timezone(timedelta(hours=-8)) # Pre-set for PST
            
            tz = ZoneInfo(timezone)
            # Add in time-zone
            start = start.replace(tzinfo=tz)
            end = end.replace(tzinfo=tz)

            # Perform past check
            now = datetime.now(tz=tz) # Set timezone for now to ensure stable deployment in prod environment
            if start < now or end < now: raise TimeValidationError(message="Time cannot be in past") # Remember to pass off message in front end
            if end <= start: raise TimeValidationError(message="End of time period cannot be less than or equal to the start")
            # Perform month and day range checks
            day_values = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
            # Return -1 as default to avoid key-error, shouldn't occur though
            if not start.weekday() == day_values.get(key, -1):
                raise TimeValidationError(message=f"Day value for {key} is not a {key}! Please enter a proper numbered day.")
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
            availability_in_iso.add(key, [start_iso, end_iso])
    return availability_in_iso

def generate_availability(day_of_week_availability: MultiDict, reoccurring_data: dict, months: int) -> MultiDict:
    """
    Generates the appropriate availability periods based on the user's input for availability periods for each day of the week.

    Availability periods marked as re-occurring based on data from form submission in "reoccurring_data" will have future day-of-week associated dates and time generated and added to the return MultiDict.

    Availability periods not marked as re-occurring will only be added once.

    Input formats:
        day_of_week_availability: 
        {'Monday': ['2025-02-01 01:01:00-08:00', '2025-02-03 01:01:00-08:00']}
        Note this input again does not have the "T" separator.

        reoccurring_data:
        {'Monday': 'false',
         'Tuesday': 'true',
         etc...}

        months: integer representing approximation of months based on multiplication of 30 days internally.

    Returns: MultiDict containing availability periods for all days-of-week that had date/times input. 
    """
    
    generated_availability = MultiDict()
    for day, period in day_of_week_availability.lists():
        # Just skip over the day if there is no period input
        if period[0] == '':
            continue
        if reoccurring_data[('repeat_' + str(day))] == 'false' and period[0] != '':
            generated_availability.add(day, [period[0], period[1]])
            # Do not generate reoccuring data
            continue
        
        # If the value is 'true' for 'repeat_x' generate the repeating periods
        # Period is a 2 element list. Period[0] is the beginning period.
        begin_date = datetime.fromisoformat(period[0])
        # Approximate 2 months out by doing 60 days, can make this more accurate in the future
        in_future = timedelta(days=months * 30)
        end_date = begin_date + in_future
        day_of_week = begin_date.weekday()
        # Generate the proper repeating elements
        # Define the start and end time of availability
        start_time = begin_date.time()
        end_time = datetime.fromisoformat(period[1]).time()

        repeating_periods = [
            [datetime.combine(d, start_time).isoformat(), datetime.combine(d, end_time).isoformat()]
            for d in (begin_date + timedelta(days=i) for i in range((end_date - begin_date).days + 1))
            if d.weekday() == day_of_week]
        
        # Add repeating elements back to the MultiDict
        generated_availability.setlist(day, repeating_periods)
        
    return generated_availability




def get_booking_slots(database) -> list[list[datetime]]:
    """
    Booking slots to be used by front-end for display.
    Currently is day-of-week agnostic as it doesn't include that data since front-end doesn't need it for appointment picking.
    Only retrieves those that are NOT booked.

    Input: database reference for connection.

    Returns: dict containing datetime appointment slots.
    """
    # perform query on availability_period in database to retrieve open time slots for each day of the week
    time_periods = database.retrieve_availability_periods()
    
    # Iterate over the time slots, segmenting them into 30 minute time slots and store them in a dictionary to the assocciated day of the week
    # Return dictionary containing segmented booking slots
    booking_slots = []
    # Remove the day-of-week info
    for period in time_periods:
        booking_slots.append([period['start']])
    
    return booking_slots
    

def split_into_30min_segments(begin_time: datetime, end_time: datetime) -> list[datetime]:
    """
    Helper function that splits a given availability period into appropriate 30 minute segments.

    Input: two datetime objects representing availability period begin and end.
        Note: Input is datetime not the string iso-format used in other functions due to ease of getting time segments with datetime module.

    Returns: list containing datetime booking slots for given period.
    """
    end_hours = end_time.time().hour
    end_minutes = end_time.time().minute
    begin_hours = begin_time.time().hour
    begin_minutes = begin_time.time().minute
    # Must include tzinfo so datetime objects are aware othereise db won't normalize to UTC correctly, depending on what it has set as its timezone
    tz = begin_time.tzinfo
    
    time_slots = []
    # Include bottom of the hour if 0 minutes
    if begin_minutes == 0:
        time_slots.append(datetime(begin_time.year, begin_time.month, begin_time.day, begin_hours, 0, tzinfo=tz))
    # 30 minute time slot starts from time generated
    # Only include minutes start if under 30 minutes
    # If minutes is above '30', go to next availale hour since meetings are a minimum of 30 minute slots
    if begin_minutes < 30:
        time_slots.append(datetime(begin_time.year, begin_time.month, begin_time.day, begin_hours, 30, tzinfo=tz))
    # Start iterating from begin_hours + 1 since we handled the minutes case above
    # Iterate starting from the first hour past the start period's minute case and go to end period's hour exlusive so we don't append 30 minutes past
    for i in range(1, ((end_hours - begin_hours))):
        # Start by appendin bottom of hour
        time_slots.append(datetime(begin_time.year, begin_time.month, begin_time.day, begin_hours+i, tzinfo=tz))
        # Append 
        time_slots.append(datetime(begin_time.year, begin_time.month, begin_time.day, begin_hours+i, 30, tzinfo=tz))
    # If end time period has more than 30 minutes available, append that period from bottom of the hour
    if end_minutes >= 30:
        time_slots.append(datetime(end_time.year, end_time.month, begin_time.day, end_hours, tzinfo=tz))
    return time_slots

def _map_to_iso(availability_period_record):
    temp_dict = {}
    day_of_week = availability_period_record['day_of_week']
    start = availability_period_record['start']
    end = availability_period_record['end']
    temp_dict[day_of_week] = [start.isoformat(), end.isoformat()]
    return temp_dict



    