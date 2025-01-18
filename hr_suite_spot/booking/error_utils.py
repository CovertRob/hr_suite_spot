# Custom exceptions to be used throughout the project.

class TimeValidationError(Exception):
    """
    To be raised when an error in converting the time inputs to ISO format is encountered. 
    May be raised under the following circumstances: 
        1. Time input was in the past
        2. Time input matched input format but not valid ISO ranges
        3. Leap year is not handled if it is a valid leap year
        4. The input day range for given month does not meet valid range
    """
    # By default Exception class takes a tuple of arguments
    def __init__(self, *args):
        super().__init__(*args)