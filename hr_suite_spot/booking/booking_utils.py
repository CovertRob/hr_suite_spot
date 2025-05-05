# Utility functions for booking functionality
# Import MultiDict for form input handling
from werkzeug.datastructures import MultiDict
import re
from datetime import datetime, timedelta
from .error_utils import TimeValidationError
from pprint import pprint
from zoneinfo import ZoneInfo
import re
import phonenumbers
from flask import flash, redirect, url_for
from email_validator import validate_email, EmailNotValidError

def slots_are_valid(slots: list[dict], *, timezone: str = "UTC") -> bool:
    """
    Return True iff every slot passes:
      • start/end parse
      • end > start
      • both instants are in the future (relative to *timezone*)
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return False   # unknown tz string

    now = datetime.now(tz)

    for slot in slots:
        try:
            raw_start = slot["start"]
            raw_end   = slot["end"]
        except KeyError:
            return False

        try:
            start = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            end   = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
        except ValueError:
            return False

        start = start.astimezone(tz)
        end   = end.astimezone(tz)

        if start <= now or end <= now:
            return False
        if end <= start:
            return False

    return True

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
    if begin_minutes == 30:
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
        time_slots.append(datetime(end_time.year, end_time.month, end_time.day, end_hours, tzinfo=tz))
    pprint(time_slots)
    return time_slots

def sanitize_phone(phone):
    # Maximum allowed input length to avoid oversized input injections.
    MAX_PHONE_LENGTH = 50

    # Step 1: Remove any leading or trailing whitespace.
    phone = phone.strip()

    # Step 2: Ensure the input does not exceed the allowed length.
    if len(phone) > MAX_PHONE_LENGTH:
        flash('Phone number input is too long', 'error')
        return redirect(url_for('get_contact'))

    # Step 3: Use a regex to ensure only allowed characters are present.
    # Allowed characters: an optional leading '+', digits, spaces, hyphens, and parentheses.
    allowed_pattern = re.compile(r'^\+?[0-9\-\(\)\s]+$')
    if not allowed_pattern.fullmatch(phone):
        flash('Phone contains disallowed characters', 'error')
        return redirect(url_for('get_contact'))

    # Step 4: Use the phonenumbers library to parse and validate the phone number.
    try:
        # If the number starts with '+', it's likely an international format.
        if phone.startswith('+'):
            parsed_phone = phonenumbers.parse(phone, None)
        else:
            # Assume 'US' as the default region if no international prefix is provided.
            parsed_phone = phonenumbers.parse(phone, 'US')
    except phonenumbers.NumberParseException:
        flash('Invalid phone number format', 'error')
        return redirect(url_for('get_contact'))

    # Step 5: Validate that the parsed phone is both "possible" and "valid."
    if not phonenumbers.is_possible_number(parsed_phone) or not phonenumbers.is_valid_number(parsed_phone):
        flash('Phone number is not valid', 'error')
        return redirect(url_for('get_contact'))

    # Step 6: Format the phone number in a canonical, international E.164 format.
    formatted_phone = phonenumbers.format_number(parsed_phone, phonenumbers.PhoneNumberFormat.E164)
    return formatted_phone

def sanitize_email(email):
    # Step 1: Remove leading and trailing whitespace.
    email = email.strip()
    
    # Step 2: Enforce a maximum allowed length to prevent oversized input.
    MAX_EMAIL_LENGTH = 254  # 254 characters is a common maximum for email addresses by RFC 5321 / 5322 standards
    if len(email) > MAX_EMAIL_LENGTH:
        flash('Email input is too long', 'error')
        return redirect(url_for('get_contact'))
    
    # Step 3: Preliminary regex check for allowed characters and basic structure.
    # This regex accommodates common email characters and ensures a basic user@domain.tld format.
    allowed_pattern = re.compile(
        r'^[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+'
        r'@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*'
        r'\.[A-Za-z]{2,}$'
    )
    if not allowed_pattern.fullmatch(email):
        flash('Email contains disallowed characters or is not formatted correctly', 'error')
        return redirect(url_for('get_contact'))
    
    # Step 4: Use the email_validator library to parse, validate, and normalize the email address.
    try:
        valid = validate_email(email)
        normalized_email = valid.email  # The normalized and validated email address.
    except EmailNotValidError as e:
        flash(f'Invalid email format: {str(e)}', 'error')
        return redirect(url_for('get_contact'))
    
    # Step 5: Return the normalized email address.
    return normalized_email

from flask import flash, redirect, url_for

def sanitize_email_body(body):
    """
    Sanitizes the body text of an email message.
    
    The function:
      1. Trims leading and trailing whitespace.
      2. Enforces a maximum length (to avoid oversized inputs).
      3. Checks for disallowed control characters (allowing only common whitespace).
      4. Returns the sanitized body (or redirects with an error if any validation fails).
    """
    
    # Step 1: Remove leading/trailing whitespace.
    body = body.strip()
    
    # Step 2: Enforce a maximum allowed length (e.g., 10000 characters).
    MAX_BODY_LENGTH = 1000
    if len(body) > MAX_BODY_LENGTH:
        flash('Email message is too long. Max 1000 characters.', 'error')
        return redirect(url_for('get_contact'))
    
    # Step 3: Check for disallowed control characters.
    # Allow: newline (LF, \n), carriage return (CR, \r), and tab (\t).
    allowed_control_codes = {9, 10, 13}  # Tab, LF, CR
    # Reject any other control characters in the range U+0000-U+001F.
    for ch in body:
        if ord(ch) < 32 and ord(ch) not in allowed_control_codes:
            flash('Email message contains disallowed characters', 'error')
            return redirect(url_for('get_contact'))
    
    # Step 4: Return the sanitized email body.
    return body



    