"""Prepare explanatory text for manuscript settings tables."""
import re


JOB_NOTE = 'Complete simulation-job definitions are listed in Table S20.17, with one job per row.'

LOCAL = re.compile(r'(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp)/)[^\s"<>]+')

def display_values(block, header, values):
    """Transform explanatory text only; CSVs retain the complete run records."""
    result = list(values)
    if block in ('S17.7','S20.7','S20.2','S20.3') and 'path' in header and 'value' in header:
        key = values[header.index('path')]
        idx = header.index('value')
        if key == '/jobs':
            result[idx] = JOB_NOTE
        else:
            result[idx] = LOCAL.sub(lambda m: re.split(r'[\\/]',m.group())[-1],result[idx])
    return result
