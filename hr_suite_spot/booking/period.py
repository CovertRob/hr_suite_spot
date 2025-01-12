# Custom time period class used for the implementation of booking calendar
from datetime import datetime


"""
Defined as a pair of datetime objects.
"""
class Period:

    def __init__(self, begin_period: datetime, end_period: datetime):
        self.begin_period = begin_period
        self.end_period = end_period

    @property
    def begin_period(self):
        return self.begin_period
    
    @begin_period.setter
    def begin_period(self, begin_period):
        self._begin_period = begin_period

    @property
    def end_period(self):
        return self.end_period
    
    @begin_period.setter
    def begin_period(self, end_period):
        self._end_period = end_period

# Note to self - make helper to check timezones for inputs