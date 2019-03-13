"""
# Collect data generated by thunderfish.
"""

import os
import sys
import argparse
from .version import __version__, __year__
from .tabledata import TableData


def collect_fish(files, insert_file=True, append_file=False,
                 harmonics=None, peaks0=None, peaks1=None):
    """
    Combine all *-wavefish.* and/or *-pulsefish.* files into respective summary tables.

    Data from the *-wavespectrum-*.* and the *-pulsepeaks-*.* files can be added
    as specified by `harmonics`, `peaks0`, and `peaks1`.

    Parameters
    ----------
    files: list of strings
        Files to be combined.
    insert_file: boolean
        Insert the basename of the recording file as the first column.
    append_file: boolean
        Add the basename of the recording file as the last column.
    harmonics: int
        Number of harmonic to be added to the wave-type fish table (amplitude, relampl, phase).
        This data is read in from the corresponding *-wavespectrum-*.* files.
    peaks0: int
        Index of the first peak of a EOD pulse to be added to the pulse-type fish table.
        This data is read in from the corresponding *-pulsepeaks-*.* files.
    peaks1: int
        Index of the last peak of a EOD pulse to be added to the pulse-type fish table.
        This data is read in from the corresponding *-pulsepeaks-*.* files.

    Returns
    -------
    wave_table: TableData
        Summary table for all wave-type fish.
    pulse_table: TableData
        Summary table for all pulse-type fish.
    """
    if append_file and insert_file:
        append_file = False
    # load data:    
    wave_table = None
    pulse_table = None
    for file_name in files:
        # file name:
        table = None
        base_path, file_ext = os.path.splitext(file_name)[0:2]
        if base_path.endswith('-pulsefish'):
            base_path = base_path[:-10]
            fish_type = 'pulse'
        elif base_path.endswith('-wavefish'):
            base_path = base_path[:-9]
            fish_type = 'wave'
        else:
            continue
        recording = os.path.basename(base_path)
        # data:
        data = TableData(file_name)
        table = wave_table if fish_type == 'wave' else pulse_table
        # prepare table:
        if not table:
            df = TableData(data)
            df.clear_data()
            if insert_file:
                for s in range(data.nsecs):
                    df.insert_section(0, 'recording')
                df.insert(0, 'recording', '', '%-s')
            if fish_type == 'wave':
                if harmonics is not None:
                    wave_spec = TableData(base_path + '-wavespectrum-0' + file_ext)
                    if data.nsecs > 0:
                        df.append_section('harmonics')
                    for h in range(harmonics+1):
                        df.append('ampl%d' % h, wave_spec.unit('amplitude'),
                                      wave_spec.format('amplitude'))
                        if h > 0:
                            df.append('relampl%d' % h, '%', '%.2f')
                            df.append('phase%d' % h, 'rad', '%.3f')
            else:
                if peaks0 is not None:
                    pulse_peaks = TableData(base_path + '-pulsepeaks-0' + file_ext)
                    if data.nsecs > 0:
                        df.append_section('peaks')
                    for p in range(peaks0, peaks1+1):
                        if p != 1:
                            df.append('P%dtime' % p, 'ms', '%.3f')
                        df.append('P%dampl' % p, pulse_peaks.unit('amplitude'),
                                  pulse_peaks.format('amplitude'))
                        if p != 1:
                            df.append('P%drelampl' % p, '%', '%.2f')
                        df.append('P%dwidth' % p, 'ms', '%.3f')
            if append_file:
                for s in range(data.nsecs):
                    df.append_section('recording')
                df.append('recording', '', '%-s')
            if fish_type == 'wave':
                wave_table = df
            else:
                pulse_table = df
            table = wave_table if fish_type == 'wave' else pulse_table
        # fill table:
        for r in range(data.rows()):
            data_col = 0
            if insert_file:
                table.append_data(recording, data_col)
                data_col += 1
            table.append_data(data[r,:], data_col)
            if peaks0 is not None and fish_type == 'pulse':
                pulse_peaks = TableData(base_path + '-pulsepeaks-%d'%r + file_ext)
                for p in range(peaks0, peaks1+1):
                    for r in range(pulse_peaks.rows()):
                        if pulse_peaks[r,'P'] == p:
                            break
                    else:
                        continue
                    if p != 1:
                        table.append_data(pulse_peaks[r,'time'], 'P%dtime' % p)
                    table.append_data(pulse_peaks[r,'amplitude'], 'P%dampl' % p)
                    if p != 1:
                        table.append_data(pulse_peaks[r,'relampl'], 'P%drelampl' % p)
                    table.append_data(pulse_peaks[r,'width'], 'P%dwidth' % p)
            elif harmonics is not None and fish_type == 'wave':
                wave_spec = TableData(base_path + '-wavespectrum-%d'%r + file_ext)
                for h in range(harmonics+1):
                    table.append_data(wave_spec[h,'amplitude'])
                    if h > 0:
                        table.append_data(wave_spec[h,'relampl'])
                        table.append_data(wave_spec[h,'phase'])
            if append_file:
                table.append_data(recording)
    return wave_table, pulse_table

    
def rangestr(string):
    """
    Parse string of the form N:M .
    """
    if string[0] == '=':
        string = '-' + string[1:]
    ss = string.split(':')
    v0 = v1 = None
    if len(ss) == 1:
        v0 = int(string)
        v1 = v0
    else:
        v0 = int(ss[0])
        v1 = int(ss[1])
    return (v0, v1)


def main():
    # command line arguments:
    parser = argparse.ArgumentParser(add_help=True,
        description='Summarize data generated by thunderfish in a wavefish and a pulsefish table.',
        epilog='version %s by Benda-Lab (2015-%s)' % (__version__, __year__))
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('-t', dest='table_type', default=None, choices=['wave', 'pulse'],
                        help='wave-type or pulse-type fish')
    parser.add_argument('-i', dest='insert_file', action='store_true',
                        help='insert the file name in the first column')
    parser.add_argument('-a', dest='append_file', action='store_true',
                        help='append the file name as the last column')
    parser.add_argument('-p', dest='pulse_peaks', type=rangestr,
                        default=(None, None), metavar='N:M',
                        help='add properties of peak PN to PM of pulse-type EODs to the table')
    parser.add_argument('-w', dest='harmonics', type=int, metavar='N',
                        help='add properties of first N harmonics of wave-type EODs to the table')
    parser.add_argument('-r', dest='remove_cols', action='append', default=[], metavar='COLUMN',
                        help='columns to be removed from output table')
    parser.add_argument('-o', dest='out_path', metavar='PATH', default='.', type=str,
                        help='path where to store summary tables')
    parser.add_argument('-f', dest='format', default=None, type=str,
                        choices=TableData.formats,
                        help='file format used for saving summary tables')
    parser.add_argument('file', nargs='+', default='', type=str,
                        help='a *-wavefish.* or *-pulsefish.* file as generated by thunderfish')
    # fix minus sign issue:
    ca = []
    pa = False
    for a in sys.argv[1:]:
        if pa and a[0] == '-':
            a = '=' + a[1:]
        pa = False
        if a == '-p':
            pa = True
        ca.append(a)
    # read in command line arguments:    
    args = parser.parse_args(ca)
    table_type = args.table_type
    remove_cols = args.remove_cols
    out_path = args.out_path
    data_format = args.format
    # create output folder:
    if not os.path.exists(out_path):
        os.makedirs(out_path)
    # collect files:
    wave_table, pulse_table = collect_fish(args.file, args.insert_file, args.append_file,
                                           args.harmonics,
                                           args.pulse_peaks[0],  args.pulse_peaks[1])
    # output format:
    if not data_format:
        ext = os.path.splitext(args.file[0])[1][1:]
        if ext in TableData.ext_formats:
            data_format = TableData.ext_formats[ext]
        else:
            data_format = 'dat'
    # write tables:
    if pulse_table and (not table_type or table_type == 'pulse'):
        for rc in remove_cols:
            if rc in pulse_table:
                pulse_table.remove(rc)
        pulse_table.write(os.path.join(out_path, 'pulsefish'), data_format)
    if wave_table and (not table_type or table_type == 'wave'):
        for rc in remove_cols:
            if rc in wave_table:
                wave_table.remove(rc)
        wave_table.write(os.path.join(out_path, 'wavefish'), data_format)


if __name__ == '__main__':
    main()
