import datetime
import time


def get_published_parsed(d):
    """
    Helper function to get the feed/entry published_parsed in datetime format
    :param d: dictionary with keys of 'published_parsed' or 'updated_parsed'
    :return: 'published_parsed' or 'updated_parsed' field in datetime format if one of them is None.
    otherwise return None
    """
    published_parsed_list = [d.get('published_parsed', None), d.get('updated_parsed', None)]
    published_parsed = None
    first = next((item for item in published_parsed_list if item is not None), None)
    if first:
        published_parsed = datetime.datetime.fromtimestamp(time.mktime(first), tz=datetime.timezone.utc)
    return published_parsed
