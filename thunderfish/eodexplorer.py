"""
View and explore properties of EOD waveforms.
"""

import os
import glob
import sys
import argparse
import numpy as np
import scipy.signal as sig
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from multiprocessing import Pool, freeze_support, cpu_count
from .version import __version__, __year__
from .configfile import ConfigFile
from .tabledata import TableData, add_write_table_config, write_table_args
from .dataloader import load_data
from .multivariateexplorer import MultivariateExplorer
from .eodanalysis import wave_quality, wave_quality_args, add_eod_quality_config
from .eodanalysis import pulse_quality, pulse_quality_args
from .powerspectrum import decibel
from .bestwindow import find_best_window, plot_best_data
from .thunderfish import configuration, detect_eods, plot_eods


            
class EODExplorer(MultivariateExplorer):
    
    def __init__(self, data, data_cols, wave_fish, eod_data,
                 add_waveforms, loaded_spec, rawdata_path, cfg):
        self.wave_fish = wave_fish
        self.eoddata = data
        self.path = rawdata_path
        MultivariateExplorer.__init__(self, data[:,data_cols],
                                      None, 'EODExplorer')
        tunit = 'ms'
        dunit = '1/ms'
        if wave_fish:
            tunit = '1/EODf'        
            dunit = 'EODf'
        wave_data = eod_data
        xlabels = ['Time [%s]' % tunit]
        ylabels = ['Voltage']
        if 'first' in add_waveforms:
            # first derivative:
            if loaded_spec:
                if hasattr(sig, 'savgol_filter'):
                    derivative = lambda x: (np.column_stack((x[0], \
                        sig.savgol_filter(x[0][:,1], 5, 2, 1, x[0][1,0]-x[0][0,0]))), x[1])
                else:
                    derivative = lambda x: (np.column_stack((x[0][:-1,:], \
                        np.diff(x[0][:,1])/(x[0][1,0]-x[0][0,0]))), x[1])
            else:
                if hasattr(sig, 'savgol_filter'):
                    derivative = lambda x: np.column_stack((x, \
                        sig.savgol_filter(x[:,1], 5, 2, 1, x[1,0]-x[0,0])))
                else:
                    derivative = lambda x: np.column_stack((x[:-1,:], \
                        np.diff(x[:,1])/(x[1,0]-x[0,0])))
            wave_data = list(map(derivative, wave_data))
            ylabels.append('dV/dt [%s]' % dunit)
            if 'second' in add_waveforms:
                # second derivative:
                if loaded_spec:
                    if hasattr(sig, 'savgol_filter'):
                        derivative = lambda x: (np.column_stack((x[0], \
                            sig.savgol_filter(x[0][:,1], 5, 2, 2, x[0][1,0]-x[0][0,0]))), x[1])
                    else:
                        derivative = lambda x: (np.column_stack((x[0][:-1,:], \
                            np.diff(x[0][:,2])/(x[0][1,0]-x[0][0,0]))), x[1])
                else:
                    if hasattr(sig, 'savgol_filter'):
                        derivative = lambda x: np.column_stack((x, \
                            sig.savgol_filter(x[:,1], 5, 2, 2, x[1,0]-x[0,0])))
                    else:
                        derivative = lambda x: np.column_stack((x[:-1,:], \
                            np.diff(x[:,2])/(x[1,0]-x[0,0])))
                wave_data = list(map(derivative, wave_data))
                ylabels.append('d^2V/dt^2 [%s^2]' % dunit)
        if loaded_spec:
            if wave_fish:
                indices = [0]
                phase = False
                xlabels.append('Harmonics')
                if 'ampl' in add_waveforms:
                    indices.append(3)
                    ylabels.append('Ampl [%]')
                if 'power' in add_waveforms:
                    indices.append(4)
                    ylabels.append('Power [dB]')
                if 'phase' in add_waveforms:
                    indices.append(5)
                    ylabels.append('Phase')
                    phase = True
                def get_spectra(x):
                    y = x[1][:,indices]
                    if phase:
                        y[y[:,-1]<0.0,-1] += 2.0*np.pi 
                    return (x[0], y)
                wave_data = list(map(get_spectra, wave_data))
            else:
                xlabels.append('Frequency [Hz]')
                ylabels.append('Power [dB]')
                def get_spectra(x):
                    y = x[1]
                    y[:,1] = decibel(y[:,1], None)
                    return (x[0], y)
                wave_data = list(map(get_spectra, wave_data))
        self.set_wave_data(wave_data, xlabels, ylabels, True)

        
    def fix_scatter_plot(self, ax, data, label, axis):
        if any(l in label for l in ['ampl', 'power', 'width',
                                    'time', 'tau', 'var', 'peak', 'trough',
                                    'dist', 'rms', 'noise']):
            if np.all(data >= 0.0):
                if axis == 'x':
                    ax.set_xlim(0.0, None)
                elif axis == 'y':
                    ax.set_ylim(0.0, None)
                elif axis == 'c':
                    return 0.0, np.max(data), None
            else:
                if axis == 'x':
                    ax.set_xlim(None, 0.0)
                elif axis == 'y':
                    ax.set_ylim(None, 0.0)
                elif axis == 'c':
                    return np.min(data), 0.0, None
        elif 'phase' in label:
            if axis == 'x':
                ax.set_xlim(-np.pi, np.pi)
                ax.set_xticks(np.arange(-np.pi, 1.5*np.pi, 0.5*np.pi))
                ax.set_xticklabels([u'-\u03c0', u'-\u03c0/2', '0', u'\u03c0/2', u'\u03c0'])
            elif axis == 'y':
                ax.set_ylim(-np.pi, np.pi)
                ax.set_yticks(np.arange(-np.pi, 1.5*np.pi, 0.5*np.pi))
                ax.set_yticklabels([u'-\u03c0', u'-\u03c0/2', '0', u'\u03c0/2', u'\u03c0'])
            elif axis == 'c':
                if ax is not None:
                    ax.set_yticklabels([u'-\u03c0', u'-\u03c0/2', '0', u'\u03c0/2', u'\u03c0'])
                return -np.pi, np.pi, np.arange(-np.pi, 1.5*np.pi, 0.5*np.pi)
        elif 'species' in label:
            if axis == 'x':
                for label in ax.get_xticklabels():
                    label.set_rotation(30)
                ax.set_xlabel('')
                ax.set_xlim(np.min(data)-0.5, np.max(data)+0.5)
            elif axis == 'y':
                ax.set_ylabel('')
                ax.set_ylim(np.min(data)-0.5, np.max(data)+0.5)
            elif axis == 'c':
                if ax is not None:
                    ax.set_ylabel('')
        return np.min(data), np.max(data), None

    
    def fix_waveform_plot(self, axs, indices):
        if len(indices) == 0:
            axs[0].text(0.5, 0.5, 'Click to plot EOD waveforms',
                        transform = axs[0].transAxes, ha='center', va='center')
            axs[0].text(0.5, 0.3, 'n = %d' % len(self.raw_data),
                        transform = axs[0].transAxes, ha='center', va='center')
        elif len(indices) == 1:
            if 'index' in self.eoddata and \
              np.any(self.eoddata[:,'index'] != self.eoddata[0,'index']):
                axs[0].set_title('%s: %d' % (self.eoddata[indices[0],'file'],
                                             self.eoddata[indices[0],'index']))
            else:
                axs[0].set_title(self.eoddata[indices[0],'file'])
            axs[0].text(0.05, 0.85, '%.1fHz' % self.eoddata[indices[0],'EODf'],
                        transform = axs[0].transAxes)
        else:
            axs[0].set_title('%d EOD waveforms selected' % len(indices))
        for ax in axs:
            for l in ax.lines:
                l.set_linewidth(3.0)
        for ax, xl in zip(axs, self.wave_ylabels):
            if 'Voltage' in xl:
                ax.set_ylim(top=1.1)
                ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=4))
            if 'dV/dt' in xl:
                ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=4))
            if 'd^2V/dt^2' in xl:
                ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=4))
        if self.wave_fish:
            for ax, xl in zip(axs, self.wave_ylabels):
                if 'Voltage' in xl:
                    ax.set_xlim(-0.7, 0.7)
                if 'Ampl' in xl or 'Power' in xl or 'Phase' in xl:
                    ax.set_xlim(-0.5, 8.5)
                    for l in ax.lines:
                        l.set_marker('.')
                        l.set_markersize(15.0)
                        l.set_markeredgewidth(0.5)
                        l.set_markeredgecolor('k')
                        l.set_markerfacecolor(l.get_color())
                if 'Ampl' in xl:
                    ax.set_ylim(0.0, 100.0)
                    ax.yaxis.set_major_locator(ticker.MultipleLocator(25.0))
                if 'Power' in xl:
                    ax.set_ylim(-60.0, 2.0)
                    ax.yaxis.set_major_locator(ticker.MultipleLocator(20.0))
                if 'Phase' in xl:
                    ax.set_ylim(0.0, 2.0*np.pi)
                    ax.set_yticks(np.arange(0.0, 2.5*np.pi, 0.5*np.pi))
                    ax.set_yticklabels(['0', u'\u03c0/2', u'\u03c0', u'3\u03c0/2', u'2\u03c0'])
        else:
            for ax, xl in zip(ax, self.wave_ylabels):
                if 'Voltage' in xl:
                    ax.set_xlim(-0.5, 1.5)
                if 'Power' in xl:
                    ax.set_xlim(1.0, 2000.0)
                    ax.set_xscale('log')
                    ax.set_ylim(-60.0, 2.0)
                    ax.yaxis.set_major_locator(ticker.MultipleLocator(20.0))
        if len(indices) > 0:
            for ax in axs:
                ax.axhline(c='k', lw=1)

            
    def list_selection(self, indices):
        if 'index' in self.eoddata and \
           np.any(self.eoddata[:,'index'] != self.eoddata[0,'index']):
            for i in indices:
                print('%s : %d' % (self.eoddata[i,'file'], self.eoddata[i,'index']))
        else:
            for i in indices:
                print(self.eoddata[i,'file'])
        if len(indices) == 1:
            # write eoddata line on terminal:
            keylen = 0
            keys = []
            values = []
            for c in range(self.eoddata.columns()):
                k, v = self.eoddata.key_value(indices[0], c)
                keys.append(k)
                values.append(v)
                if keylen < len(k):
                    keylen = len(k)
            for k, v in zip(keys, values):
                fs = '%%-%ds: %%s' % keylen
                print(fs % (k, v.strip()))

                
    def analyze_selection(self, index):
        # load data:
        basename = self.eoddata[index,'file']
        bp = os.path.join(self.path, basename)
        fn = glob.glob(bp + '.*')
        if len(fn) == 0:
            print('no recording found for %s' % bp)
            return
        recording = fn[0]
        channel = 0
        try:
            raw_data, samplerate, unit = load_data(recording, channel)
        except IOError as e:
            print('%s: failed to open file: %s' % (recording, str(e)))
            return
        if len(raw_data) <= 1:
            print('%s: empty data file' % recording)
            return
        # load configuration:
        cfgfile = __package__ + '.cfg'
        cfg = configuration(cfgfile, False, recording)
        if 'flipped' in self.eoddata:
            fs = 'flip' if self.eoddata[index,'flipped'] else 'none'
            cfg.set('flipWaveEOD', fs)
            cfg.set('flipPulseEOD', fs)
        # best_window:
        data, idx0, idx1, clipped = find_best_window(raw_data, samplerate, cfg)
        # detect EODs in the data:
        pulse_fish, psd_data, fishlist, _, eod_props, _, _, mean_eods, \
          spec_data, peak_data, power_thresh, skip_reason = \
          detect_eods(data, samplerate, clipped, recording, 0, cfg)
        # plot EOD:
        idx = int(self.eoddata[index,'index']) if 'index' in self.eoddata else 0
        for k in ['toolbar', 'keymap.back', 'keymap.forward', 'keymap.zoom', 'keymap.pan']:
            plt.rcParams[k] = self.plt_params[k]
        fig = plot_eods(basename, raw_data, samplerate, idx0, idx1, clipped, fishlist,
                        mean_eods, eod_props, peak_data, spec_data, [idx], unit,
                        psd_data, cfg.value('powerNHarmonics'), True, 3000.0,
                        interactive=True)
        fig.canvas.set_window_title('thunderfish: %s' % basename)
        plt.show(block=False)

        
class PrintHelp(argparse.Action):
    def __call__(self, parser, namespace, values, option_string):
        parser.print_help()
        print('')
        print('mouse:')
        for ma in MultivariateExplorer.mouse_actions:
            print('%-23s %s' % ma)
        print('')
        print('key shortcuts:')
        for ka in MultivariateExplorer.key_actions:
            print('%-23s %s' % ka)
        parser.exit()      

        
wave_fish = True
load_spec = False
data = None
data_path = None

def load_waveform(idx):
    eodf = data[idx,'EODf']
    file_name = data[idx,'file']
    file_index = data[idx,'index'] if 'index' in data else 0
    eod_table = TableData(os.path.join(data_path, '%s-eodwaveform-%d.csv' % (file_name, file_index)))
    eod = eod_table[:,'mean']
    norm = np.max(eod)
    if wave_fish:
        eod = np.column_stack((eod_table[:,'time']*0.001*eodf, eod/norm))
    else:
        eod = np.column_stack((eod_table[:,'time'], eod/norm))
    if not load_spec:
        return eod
    fish_type = 'wave' if wave_fish else 'pulse'
    spec_table = TableData(os.path.join(data_path, '%s-%sspectrum-%d.csv' % (file_name, fish_type, file_index)))
    spec_data = spec_table.array()
    if not wave_fish:
        spec_data = spec_data[spec_data[:,0]<2000.0,:]
        spec_data = spec_data[::5,:]
    return (eod, spec_data)
        

def main():
    global data
    global wave_fish
    global load_spec
    global data_path

    # command line arguments:
    parser = argparse.ArgumentParser(add_help=False,
        description='View and explore properties of EOD waveforms.',
        epilog='version %s by Benda-Lab (2019-%s)' % (__version__, __year__))
    parser.add_argument('-h', '--help', nargs=0, action=PrintHelp,
                        help='show this help message and exit')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('-l', dest='list_columns', action='store_true',
                        help='list all available data columns and exit')
    parser.add_argument('-j', dest='jobs', nargs='?', type=int, default=None, const=0,
                        help='number of jobs run in parallel for loading waveform data. Without argument use all CPU cores.')
    parser.add_argument('-D', dest='column_groups', default=[], type=str, action='append',
                        choices=['all', 'allpower', 'noise', 'timing', 'ampl', 'relampl', 'power', 'relpower', 'phase', 'time', 'width', 'none'],
                        help='default selection of data columns, check them with the -l option')
    parser.add_argument('-d', dest='add_data_cols', action='append', default=[], metavar='COLUMN',
                        help='data columns to be appended or removed (if already listed) for analysis')
    parser.add_argument('-n', dest='max_harmonics', default=0, type=int, metavar='MAX',
                        help='maximum number of harmonics or peaks to be used')
    parser.add_argument('-w', dest='add_waveforms', default=[], type=str, action='append',
                        choices=['first', 'second', 'ampl', 'power', 'phase'],
                        help='add first or second derivative of EOD waveform, or relative amplitude, power, or phase to the plot of selected EODs.')
    parser.add_argument('-s', dest='save_pca', action='store_true',
                        help='save PCA components and exit')
    parser.add_argument('-c', dest='color_col', default='EODf', type=str, metavar='COLUMN',
                        help='data column to be used for color code or "index"')
    parser.add_argument('-m', dest='color_map', default='jet', type=str, metavar='CMAP',
                        help='name of color map')
    parser.add_argument('-p', dest='data_path', default='.', type=str, metavar='PATH',
                        help='path to the analyzed EOD waveform data')
    parser.add_argument('-P', dest='rawdata_path', default='.', type=str, metavar='PATH',
                        help='path to the raw EOD recordings')
    parser.add_argument('-f', dest='format', default='auto', type=str,
                        choices=TableData.formats + ['same'],
                        help='file format used for saving PCA data ("same" uses same format as input file)')
    parser.add_argument('file', default='', type=str,
                        help='a wavefish.* or pulsefish.* summary file as generated by collectfish')
    args = parser.parse_args()
        
    # read in command line arguments:    
    list_columns = args.list_columns
    jobs = args.jobs
    file_name = args.file
    column_groups = args.column_groups
    add_data_cols = args.add_data_cols
    max_harmonics = args.max_harmonics
    add_waveforms = args.add_waveforms
    save_pca = args.save_pca
    color_col = args.color_col
    color_map = args.color_map
    data_path = args.data_path
    rawdata_path = args.rawdata_path
    data_format = args.format
    
    # read configuration:
    cfgfile = __package__ + '.cfg'
    cfg = ConfigFile()
    add_eod_quality_config(cfg)
    add_write_table_config(cfg, table_format='csv', unitstyle='row', format_width=True,
                           shrink_width=False)
    cfg.load_files(cfgfile, file_name, 3)
    
    # output format:
    if data_format == 'same':
        ext = os.path.splitext(file_name)[1][1:]
        if ext in TableData.ext_formats:
            data_format = TableData.ext_formats[ext]
        else:
            data_format = 'dat'
    if data_format != 'auto':
        cfg.set('fileFormat', data_format)

    # check color map:
    if not color_map in plt.colormaps():
        parser.error('"%s" is not a valid color map' % color_map)
        
    # load summary data:
    wave_fish = 'wave' in file_name
    data = TableData(file_name)

    # basename:
    basename = os.path.splitext(os.path.basename(file_name))[0]
    
    # check quality:
    skipped = 0
    for r in reversed(range(data.rows())):
        idx = 0
        if 'index' in data:
            idx = data[r,'index']
        clipped = 0.0
        if 'clipped' in data:
            clipped = 0.01*data[r,'clipped']
        skips = ''
        if wave_fish:
            harm_rampl = np.array([data[r,'relampl%d'%(k+1)] for k in range(3)])
            skips, msg = wave_quality(idx, clipped, 0.01*data[r,'noise'],
                                      0.01*data[r,'rmserror'],
                                      data[r,'power'], 0.01*harm_rampl,
                                      **wave_quality_args(cfg))
        else:
            skips, msg = pulse_quality(idx, clipped, 0.01*data[r,'noise'],
                                       **pulse_quality_args(cfg))
        if len(skips) > 0:
            print('skip fish %d from %s: %s' % (idx, data[r,'file'], skips))
            del data[r,:]
            skipped += 1
    if skipped > 0:
        print('')

    # add species column (experimental):
    if wave_fish:
        # wavefish species:
        species = np.zeros(data.rows(), object)
        species[(data[:,'phase1'] < 0) & (data[:,'EODf'] < 300.0)] = 'Sterno'
        species[(data[:,'phase1'] < 0) & (data[:,'EODf'] > 300.0)] = 'Eigen'
        species[data[:,'phase1'] > 0] = 'Aptero'
        data.append('species', '', '%d', species)

    if wave_fish:
        # maximum number of harmonics:
        if max_harmonics == 0:
            max_harmonics = 40
        else:
            max_harmonics += 1
        for k in range(1, max_harmonics):
            if not ('phase%d' % k) in data:
                max_harmonics = k
                break
    else:
        # minimum number of peaks:
        min_peaks = -10
        for k in range(1, min_peaks, -1):
            if not ('P%dampl' % k) in data or not np.all(np.isfinite(data[:,'P%dampl' % k])):
                min_peaks = k+1
                break
        # maximum number of peaks:
        if max_harmonics == 0:
            max_peaks = 20
        else:
            max_peaks = max_harmonics + 1
        for k in range(1, max_peaks):
            if not ('P%dampl' % k) in data or not np.all(np.isfinite(data[:,'P%dampl' % k])):
                max_peaks = k
                break
        
    # default columns:
    group_cols = ['EODf']
    if len(column_groups) == 0:
        column_groups = ['all']
    for group in column_groups:
        if group == 'none':
            group_cols = []
        elif wave_fish:
            if group == 'noise':
                group_cols.extend(['noise', 'rmserror',
                                   'p-p-amplitude', 'power'])
            elif group == 'timing' or group == 'time':
                group_cols.extend(['peakwidth', 'p-p-distance', 'leftpeak', 'rightpeak',
                                  'lefttrough', 'righttrough'])
            elif group == 'ampl':
                for k in range(0, max_harmonics):
                    group_cols.append('ampl%d' % k)
            elif group == 'relampl':
                for k in range(1, max_harmonics):
                    group_cols.append('relampl%d' % k)
            elif group == 'relpower' or group == 'power':
                for k in range(1, max_harmonics):
                    group_cols.append('relpower%d' % k)
            elif group == 'phase':
                for k in range(1, max_harmonics):
                    group_cols.append('phase%d' % k)
            elif group == 'all':
                for k in range(1, max_harmonics):
                    group_cols.append('relampl%d' % k)
                    group_cols.append('phase%d' % k)
            elif group == 'allpower':
                for k in range(1, max_harmonics):
                    group_cols.append('relampl%d' % k)
                    group_cols.append('relpower%d' % k)
                    group_cols.append('phase%d' % k)
            else:
                parser.error('"%s" is not a valid data group for wavefish' % group)
        else:  # pulse fish
            if group == 'noise':
                group_cols.extend(['noise', 'p-p-amplitude', 'min-ampl', 'max-ampl'])
            elif group == 'timing':
                group_cols.extend(['tstart', 'tend', 'width', 'tau', 'firstpeak', 'lastpeak'])
            elif group == 'power':
                group_cols.extend(['peakfreq', 'peakpower', 'poweratt5', 'poweratt50', 'lowcutoff'])
            elif group == 'time':
                for k in range(min_peaks, max_peaks):
                    if k != 1:
                        group_cols.append('P%dtime' % k)
            elif group == 'ampl':
                for k in range(min_peaks, max_peaks):
                    group_cols.append('P%dampl' % k)
            elif group == 'relampl':
                for k in range(min_peaks, max_peaks):
                    if k != 1:
                        group_cols.append('P%drelampl' % k)
            elif group == 'width':
                for k in range(min_peaks, max_peaks):
                    if k != 1:
                        group_cols.append('P%dwidth' % k)
            elif group == 'all':
                for k in range(min_peaks, max_peaks):
                    if k != 1:
                        group_cols.append('P%drelampl' % k)
                        group_cols.append('P%dtime' % k)
                        group_cols.append('P%dwidth' % k)
                group_cols.extend(['tau', 'peakfreq', 'poweratt5'])
            else:
                parser.error('"%s" is not a valid data group for pulsefish' % group)
    # additional data columns:
    group_cols.extend(add_data_cols)
    # translate to indices:
    data_cols = []
    for c in group_cols:
        idx = data.index(c)
        if idx is None:
            parser.error('"%s" is not a valid data column' % c)
        elif idx in data_cols:
            data_cols.remove(idx)
        else:
            data_cols.append(idx)

    # color code:
    color_idx = data.index(color_col)
    colors = None
    color_label = None
    if color_idx is None and color_col != 'index':
        parser.error('"%s" is not a valid column for color code' % color_col)
    if color_idx is None:
        colors = -2
    elif color_idx in data_cols:
        colors = data_cols.index(color_idx)
    else:
        if len(data.unit(color_idx)) > 0 and not data.unit(color_idx) in ['-', '1']:
            color_label = '%s [%s]' % (data.label(color_idx), data.unit(color_idx))
        else:
            color_label = data.label(color_idx)
        colors = data[:,color_idx]

    # list columns:
    if list_columns:
        for k, c in enumerate(data.keys()):
            s = [' '] * 3
            if k in data_cols:
                s[1] = '*'
            if k == color_idx:
                s[0] = 'C'
            print(''.join(s) + c)
        parser.exit()

    # load waveforms:
    load_spec = 'ampl' in add_waveforms or 'power' in add_waveforms or 'phase' in add_waveforms
    if jobs is not None:
        cpus = cpu_count() if jobs == 0 else jobs
        p = Pool(cpus)
        eod_data = p.map(load_waveform, range(data.rows()))
        del p
    else:
        eod_data = list(map(load_waveform, range(data.rows())))

    # explore:
    eod_expl = EODExplorer(data, data_cols, wave_fish, eod_data,
                           add_waveforms, load_spec, rawdata_path, cfg)
    # write pca:
    if save_pca:
        eod_expl.compute_pca(False)
        eod_expl.save_pca(basename, False, **write_table_args(cfg))
        eod_expl.compute_pca(True)
        eod_expl.save_pca(basename, True, **write_table_args(cfg))
    else:
        eod_expl.set_colors(colors, color_label, color_map)
        eod_expl.show()


if __name__ == '__main__':
    freeze_support()  # needed by multiprocessing for some weired windows stuff
    main()
