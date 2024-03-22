import os
import re


def get_date(x):
    """parse filename to return event name"""
    basename = os.path.basename(x)
    date = basename.split("_")[1:4]
    date = "_".join(date)
    return date


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


def get_year(path):
    date = get_date(path)
    year = date.split('_')[2]
    return year


def get_working_dir():
    test_env_set = os.environ.get("TEST_ENV")
    return "/blue/ewhite/everglades_test" if test_env_set else "/blue/ewhite/everglades"
