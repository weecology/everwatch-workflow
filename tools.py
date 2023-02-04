import os
import re

def get_date(path):
    path = os.path.basename(path)
    regex = re.compile('\\w+_(\\d+_\\d+_\\d+).*_projected')
    return regex.match(path).group(1)

def get_event(path):
    """
    Determines the event for a given UAS flight

    When there is only one event, the event is not typically recorded in the file name.
    So, values for path are of the general form:
    /path/to/file/site_month_day_year_projected.shp
    or
    /path/to/file/site_month_day_year_event_projected.shp

    This function returns "primary" for no event and events with the following values:
    "A", "a", "primary", "PRIMARY", or mixed case versions of "primary"
    """
    path = os.path.basename(path)
    regex = re.compile('\\w+_\\d+_\\d+_\\d+_(\\w+)_projected')
    match = regex.match(path)
    if match and match.group(1).upper() != "A" and match.group(1).upper() != "PRIMARY":
        return match.group(1)
    else:
        return "primary"

def get_site(path):
    path = os.path.basename(path)
    regex = re.compile("(\\w+)_\\d+_\\d+_\\d+.*_projected")
    return regex.match(path).group(1)