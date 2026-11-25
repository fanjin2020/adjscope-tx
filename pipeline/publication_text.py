"""Prepare explanatory text for manuscript settings tables."""
import re


JOB_NOTE = 'The benchmark saves the simulation job definitions in the jobs array of its output file final_results/protocol.json.'
DOWNLOAD_NOTE = 'Input definitions and download code: AdjScope-Tx v3.3.0.'
SEA_DFC_SOURCE = ('https://sea-ad-single-cell-profiling.s3.us-west-2.amazonaws.com/'
                  '?list-type=2&prefix=PFC%2FRNAseq%2Fdonors_objects%2F')

LOCAL = re.compile(r'(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp)/)[^\s"<>]+')


def publication_notes(section, frame):
    """Update reader-facing notes; the checksum-verified evidence stays unchanged."""
    if section == 'S1.2':
        frame = frame.copy()
        frame['input_specification'] = frame.input_specification.str.replace(
            'Input definitions and download code: public release v2.1.0.', DOWNLOAD_NOTE, regex=False)
        frame.loc[frame.resource.eq('SEA-AD'), 'public_source'] = SEA_DFC_SOURCE
    elif section in ('S17.7', 'S20.7'):
        frame = frame.copy()
        frame.loc[frame.path.eq('/jobs'), 'value'] = JOB_NOTE
    return frame

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
