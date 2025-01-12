"""
Calendar appointment booking function for HR Suite Spot

Problem: 

Given an input of time and date ranges from Jasmin, need to display the available time slots people can book appointments for.

Store Jasmin's availability

Compute and remove availability slots once they have been booked

Jasmin:
Input: availability range
Output: calendar for booking

User:
Input: selection of booking time
Output: confirmation of booking

Examples / Test Cases:

Data Structures:

Algorithm:
1. Compute and show availability

2. How should admin (Jasmin) input availability on front end and have it be re-occuring?

Code:
"""
import calendar
from period import Period

class BookingCalendar():

    def __init__(self, availability_periods):
        booking_calendar = calendar.Calendar()

    def input_availability(period_list: Period):
        pass
        # Pass availability periods to database here

    def parse_available_periods(input):
        pass
        # parse stream of availability here and create Period objects from it

def  main():
    pass

if __name__ == '__main__':
    main()

    

