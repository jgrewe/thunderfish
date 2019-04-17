"""
View and explore properties of EOD waveforms.
"""

import os
import glob
import sys
import argparse
import numpy as np
from sklearn import decomposition
from sklearn import preprocessing
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.widgets as widgets
from multiprocessing import Pool, freeze_support, cpu_count
from .version import __version__, __year__
from .configfile import ConfigFile
from .tabledata import TableData, add_write_table_config, write_table_args
from .dataloader import load_data
from .eodanalysis import wave_quality, wave_quality_args, add_eod_quality_config
from .eodanalysis import pulse_quality, pulse_quality_args
from .bestwindow import find_best_window, plot_best_data
from .thunderfish import configuration, detect_eods, plot_eods


class MultivariateExplorer(object):
    """Simple GUI for exploring multivariate data.

    Shown are scatter plots of all pairs of variables or PCA axis.
    Scatter plots are colored according to one of the variables.
    Data points can be selected and corresponding waveforms are shown.
    """
    
    def __init__(self, title, data, labels=None, waveform_data=None):
        """ Initialize wit the data.

        Parameter
        ---------
        title: string
            Title for the window.
        data: TableData or 2D array
            The data to be explored. Each column is a variable.
        labels: list of string
            If data is not a TableData, then this provides labels
            for the data columns.
        waveform_data: List of 2D arrays
            Waveform data associated with each row of the data.
            `data[i][:,time], data[i][:,x]`
        """
        # data and labels:
        self.title = title
        if isinstance(data, TableData):
            self.raw_data = data.array()
            if labels is None:
                self.raw_labels = []
                for c in range(len(data)):
                    self.raw_labels.append('%s [%s]' % (data.label(c), data.unit(c)))
            else:
                self.raw_labels = labels
        else:
            self.raw_data = data
            self.raw_labels = labels
        # no pca data yet:
        self.all_data = [self.raw_data, None, None]
        self.all_labels = [self.raw_labels, None, None]
        self.all_maxcols = [self.raw_data.shape[1], None, None]
        self.all_titles = ['data', 'PCA', 'scaled PCA']
        # pca:
        self.pca_tables = [None, None]
        self.pca_header(data, labels)
        # start showing raw data:
        self.show_mode = 0
        self.data = self.all_data[self.show_mode]
        self.labels = self.all_labels[self.show_mode]
        self.show_maxcols = self.all_maxcols[self.show_mode]
        # waveform data:
        self.waveform_data = waveform_data
        # colors:
        self.color_map = None
        self.extra_colors = None
        self.extra_color_label = None
        self.color_values = None
        self.color_set_index = None
        self.color_index = None
        self.color_label = None
        self.color_set_index = 0
        self.color_index = 0
        self.data_colors = None
        self.color_vmin = None
        self.color_vmax = None
        self.color_ticks = None
        self.cbax = None
        # figure variables:
        self.plt_params = {}
        for k in ['toolbar', 'keymap.quit', 'keymap.back', 'keymap.forward',
                  'keymap.zoom', 'keymap.pan', 'keymap.xscale', 'keymap.yscale']:
            self.plt_params[k] = plt.rcParams[k]
            if k != 'toolbar':
                plt.rcParams[k] = ''
        self.xborder = 70.0  # pixel for ylabels
        self.yborder = 50.0  # pixel for xlabels
        self.spacing = 10.0  # pixel between plots
        self.pick_radius = 4.0
        self.histax = []
        self.histindices = []
        self.histselect = []
        self.hist_nbins = 30
        self.corrax = []
        self.corrindices = []
        self.corrartists = []
        self.corrselect = []
        self.scatter = True
        self.mark_data = []
        self.select_zooms = False
        self.zoom_stack = []
        self.wave_ax = None
        self.zoomon = False
        self.zoom_back = None
        self.zoom_size = np.array([0.5, 0.5])

        
    def set_colors(self, colors, color_label, color_map):
        """ Set data column used to color scatter plots.
        
        Parameter
        ---------
        colors: int or 1D array
           Index to colum in data to be used for coloring scatter plots.
           Or data array used to color scaler plots.
        color_label: string
           If colors is an array, this is a label describing the data.
           It is used to label the color bar.
        color_map: string
            Name of a matplotlib color map.
        """
        if isinstance(colors, int):
            self.color_set_index = 0
            self.color_index = colors
        else:
            self.extra_colors = colors
            self.extra_color_label = color_label
            self.color_set_index = -1
            self.color_index = 1
        self.color_map = plt.get_cmap(color_map)

        
    def show(self):
        """ Show the interactive scatter plots for exploration.
        """
        plt.rcParams['toolbar'] = 'None'
        plt.rcParams['keymap.quit'] = 'ctrl+w, alt+q, q'
        self.fig = plt.figure(facecolor='white')
        self.fig.canvas.set_window_title(self.title + ': ' + self.all_titles[self.show_mode])
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.fig.canvas.mpl_connect('resize_event', self.on_resize)
        self.fig.canvas.mpl_connect('pick_event', self.on_pick)
        if self.color_map is None:
            self.color_map = plt.get_cmap('jet')
        self.set_color_column()
        self.plot_histograms()
        self.plot_correlations()
        if not self.waveform_data is None:
            self.wave_ax = self.fig.add_subplot(2, 3, 3)
            self.fix_waveform_plot(self.wave_ax, self.mark_data)
        self.plot_zoomed_correlations()
        plt.show()


    def pca_header(self, data, labels):
        if isinstance(data, TableData):
            header = data.table_header()
        else:
            lbs = []
            for l in labels:
                if '[' in l:
                    lbs.append(l.split('[')[0].strip())
                elif '/' in l:
                    lbs.append(l.split('/')[0].strip())
                else:
                    lbs.append(l)
            header = TableData(header=lbs)
        header.set_formats('%.3f')
        header.insert(0, ['PC'] + ['-']*header.nsecs, '', '%d')
        header.insert(1, 'variance', '%', '%.3f')
        for k in range(len(self.pca_tables)):
            self.pca_tables[k] = TableData(header)

                
    def compute_pca(self, scale=False, write=False):
        """ Compute PCA based on the data.

        Parameter
        ---------
        scale: boolean
            If True standardize data before computing PCA, i.e. remove mean
            of each variabel and divide by its standard deviation.
        write: boolean
            If True write PCA components to standard out.
        """
        # pca:
        pca = decomposition.PCA()
        if scale:
            scaler = preprocessing.StandardScaler()
            scaler.fit(self.raw_data)
            pca.fit(scaler.transform(self.raw_data))
            pca_label = 'sPC'
        else:
            pca.fit(self.raw_data)
            pca_label = 'PC'
        for k in range(len(pca.components_)):
            if np.abs(np.min(pca.components_[k])) > np.max(pca.components_[k]):
                pca.components_[k] *= -1.0
        pca_data = pca.transform(self.raw_data)
        pca_labels = [('%s%d (%.1f%%)' if v > 0.01 else '%s%d (%.2f%%)') % (pca_label, k+1, 100.0*v)
                           for k, v in enumerate(pca.explained_variance_ratio_)]
        if np.min(pca.explained_variance_ratio_) >= 0.01:
            pca_maxcols = pca_data.shape[1]
        else:
            pca_maxcols = np.argmax(pca.explained_variance_ratio_ < 0.01)
        if pca_maxcols < 2:
            pca_maxcols = 2
        # table with PCA feature weights:
        pca_table = self.pca_tables[1] if scale else self.pca_tables[0]
        pca_table.clear_data()
        pca_table.set_section(pca_label, 0, pca_table.nsecs)
        for k, comp in enumerate(pca.components_):
            pca_table.append_data(k+1, 0)
            pca_table.append_data(100.0*pca.explained_variance_ratio_[k])
            pca_table.append_data(comp)
        if write:
            pca_table.write(table_format='out', unitstyle='none')
        # submit data:
        if scale:
            self.all_data[2] = pca_data
            self.all_labels[2] = pca_labels
            self.all_maxcols[2] = pca_maxcols
        else:
            self.all_data[1] = pca_data
            self.all_labels[1] = pca_labels
            self.all_maxcols[1] = pca_maxcols

            
    def save_pca(self, file_name, scale, **kwargs):
        """ Write PCA data to file.

        Parameter
        ---------
        file_name: string
            Name of ouput file.
        scale: boolean
            If True write PCA components of standardized PCA.
        kwargs: dict
            Additional parameter for TableData.write()
        """
        if scale:
            pca_file = file_name + '-pcacor'
            pca_table = self.pca_tables[1]
        else:
            pca_file = file_name + '-pcacov'
            pca_table = self.pca_tables[0]
        if 'unitstyle' in kwargs:
            del kwargs['unitstyle']
        if 'table_format' in kwargs:
            pca_table.write(pca_file, unitstyle='none', **kwargs)
        else:
            pca_file += '.dat'
            pca_table.write(pca_file, unitstyle='none')

            
    def set_color_column(self):
        if self.color_set_index == -1:
            if self.color_index == 0:
                self.color_values = np.arange(self.data.shape[0], dtype=np.float)
                self.color_label = 'index'
            elif self.color_index == 1:
                self.color_values = self.extra_colors
                self.color_label = self.extra_color_label
        else:
            self.color_values = self.all_data[self.color_set_index][:,self.color_index]
            self.color_label = self.all_labels[self.color_set_index][self.color_index]
        self.color_vmin, self.color_vmax, self.color_ticks = \
          self.fix_scatter_plot(self.cbax, self.color_values, self.color_label, 'c')
        self.data_colors = self.color_map((self.color_values - self.color_vmin)/(self.color_vmax - self.color_vmin))
                    
    def plot_hist(self, ax, zoomax, keep_lims):
        ax_xlim = ax.get_xlim()
        ax_ylim = ax.get_ylim()
        try:
            idx = self.histax.index(ax)
            c = self.histindices[idx]
            in_hist = True
        except ValueError:
            idx = self.corrax.index(ax)
            c = self.corrindices[-1][0]
            in_hist = False
        ax.clear()
        ax.relim()
        ax.autoscale(True)
        ax.hist(self.data[:,c], self.hist_nbins)
        ax.set_xlabel(self.labels[c])
        self.fix_scatter_plot(ax, self.data[:,c], self.labels[c], 'x')
        if zoomax:
            ax.set_ylabel('count')
            cax = self.histax[self.corrindices[-1][0]]
            ax.set_xlim(cax.get_xlim())
        else:
            if c == 0:
                ax.set_ylabel('count')
            else:
                plt.setp(ax.get_yticklabels(), visible=False)
        if keep_lims:
            ax.set_xlim(*ax_xlim)
            ax.set_ylim(*ax_ylim)
        try:
            selector = widgets.RectangleSelector(ax, self.on_select,
                                                 drawtype='box', useblit=True, button=1,
                                                 state_modifier_keys=dict(move='', clear='', square='', center=''))
        except TypeError:
            selector = widgets.RectangleSelector(ax, self.on_select, drawtype='box',
                                                 useblit=True, button=1)
        if in_hist:
            self.histselect[idx] = selector
        else:
            self.corrselect[idx] = selector
            self.corrartists[idx] = None
        if zoomax:
            bbox = ax.get_tightbbox(self.fig.canvas.get_renderer())
            if bbox is not None:
                self.zoom_back = patches.Rectangle((bbox.x0, bbox.y0), bbox.width, bbox.height,
                                                   transform=None, clip_on=False,
                                                   facecolor='white', edgecolor='none',
                                                   alpha=0.8, zorder=-5)
                ax.add_patch(self.zoom_back)
        
    def plot_histograms(self):
        n = self.data.shape[1]
        yax = None
        self.histax = []
        for r in range(n):
            ax = self.fig.add_subplot(n, n, (n-1)*n+r+1, sharey=yax)
            self.histax.append(ax)
            self.histindices.append(r)
            self.histselect.append(None)
            self.plot_hist(ax, False, False)
            yax = ax
            
    def plot_scatter(self, ax, zoomax, keep_lims, cax=None):
        ax_xlim = ax.get_xlim()
        ax_ylim = ax.get_ylim()
        idx = self.corrax.index(ax)
        c, r = self.corrindices[idx]
        if self.scatter:
            ax.clear()
            ax.relim()
            ax.autoscale(True)
            a = ax.scatter(self.data[:,c], self.data[:,r], c=self.color_values,
                           cmap=self.color_map, vmin=self.color_vmin, vmax=self.color_vmax,
                           s=50, edgecolors='none', zorder=10)
            if cax is not None:
                self.fig.colorbar(a, cax=cax, ticks=self.color_ticks)
                cax.set_ylabel(self.color_label)
                self.color_vmin, self.color_vmax, self.color_ticks = \
                  self.fix_scatter_plot(self.cbax, self.color_values, self.color_label, 'c')
        else:
            ax.autoscale(True)
            self.fix_scatter_plot(ax, self.data[:,c], self.labels[c], 'x')
            self.fix_scatter_plot(ax, self.data[:,r], self.labels[r], 'y')
            axrange = [ax.get_xlim(), ax.get_ylim()]
            ax.clear()
            ax.hist2d(self.data[:,c], self.data[:,r], self.hist_nbins, range=axrange,
                      cmap=plt.get_cmap('Greys'))
        a = ax.scatter(self.data[self.mark_data,c], self.data[self.mark_data,r],
                       c=self.data_colors[self.mark_data], s=80, zorder=11)
        self.corrartists[idx] = a
        self.fix_scatter_plot(ax, self.data[:,c], self.labels[c], 'x')
        self.fix_scatter_plot(ax, self.data[:,r], self.labels[r], 'y')
        if zoomax:
            ax.set_xlabel(self.labels[c])
            ax.set_ylabel(self.labels[r])
            cax = self.corrax[self.corrindices[:-1].index(self.corrindices[-1])]
            ax.set_xlim(cax.get_xlim())
            ax.set_ylim(cax.get_ylim())
        else:
            plt.setp(ax.get_xticklabels(), visible=False)
            if c == 0:
                ax.set_ylabel(self.labels[r])
            else:
                plt.setp(ax.get_yticklabels(), visible=False)
        if keep_lims:
            ax.set_xlim(*ax_xlim)
            ax.set_ylim(*ax_ylim)
        if zoomax:
            bbox = ax.get_tightbbox(self.fig.canvas.get_renderer())
            if bbox is not None:
                self.zoom_back = patches.Rectangle((bbox.x0, bbox.y0), bbox.width, bbox.height,
                                                   transform=None, clip_on=False,
                                                   facecolor='white', edgecolor='none',
                                                   alpha=0.8, zorder=-5)
                ax.add_patch(self.zoom_back)
        try:
            selector = widgets.RectangleSelector(ax, self.on_select, drawtype='box',
                                                 useblit=True, button=1,
                                                 state_modifier_keys=dict(move='', clear='', square='', center=''))
        except TypeError:
            selector = widgets.RectangleSelector(ax, self.on_select, drawtype='box',
                                                 useblit=True, button=1)
        self.corrselect[idx] = selector

    def plot_correlations(self):
        self.cbax = self.fig.add_axes([0.5, 0.5, 0.1, 0.5])
        cbax = self.cbax
        n = self.data.shape[1]
        for r in range(1, n):
            yax = None
            for c in range(r):
                ax = self.fig.add_subplot(n, n, (r-1)*n+c+1, sharex=self.histax[c], sharey=yax)
                self.corrax.append(ax)
                self.corrindices.append([c, r])
                self.corrartists.append(None)
                self.corrselect.append(None)
                self.plot_scatter(ax, False, False, cbax)
                yax = ax
                cbax = None

    def plot_zoomed_correlations(self):
        ax = self.fig.add_axes([0.5, 0.9, 0.05, 0.05])
        ax.set_visible(False)
        self.zoomon = False
        c = 0
        r = 1
        ax.scatter(self.data[:,c], self.data[:,r], c=self.data_colors,
                   s=50, edgecolors='none')
        a = ax.scatter(self.data[self.mark_data,c], self.data[self.mark_data,r],
                       c=self.data_colors[self.mark_data], s=80)
        ax.set_xlabel(self.labels[c])
        ax.set_ylabel(self.labels[r])
        self.fix_scatter_plot(ax, self.data[:,c], self.labels[c], 'x')
        self.fix_scatter_plot(ax, self.data[:,r], self.labels[r], 'y')
        self.corrax.append(ax)
        self.corrindices.append([c, r])
        self.corrartists.append(a)
        self.corrselect.append(None)
                
    def fix_scatter_plot(self, ax, data, label, axis):
        """
        axis: str
          x, y: set xlim or ylim of ax
          c: return vmin, vmax, and ticks
        """
        pass

    def fix_waveform_plot(self, ax, indices):
        pass
    
    def list_selection(self, indices):
        for i in indices:
            print(i)
    
    def analyze_selection(self, index):
        pass
    
    def set_zoom_pos(self, width, height):
        if self.zoomon:
            xoffs = self.xborder/width
            yoffs = self.yborder/height
            if self.corrindices[-1][1] < self.data.shape[1]:
                idx = self.corrindices[:-1].index(self.corrindices[-1])
                pos = self.corrax[idx].get_position().get_points()
            else:
                pos = self.histax[self.corrindices[-1][0]].get_position().get_points()
            pos[0] = np.mean(pos, 0) - 0.5*self.zoom_size
            if pos[0][0] < xoffs: pos[0][0] = xoffs
            if pos[0][1] < yoffs: pos[0][1] = yoffs
            pos[1] = pos[0] + self.zoom_size
            if pos[1][0] > 1.0-self.spacing/width: pos[1][0] = 1.0-self.spacing/width
            if pos[1][1] > 1.0-self.spacing/height: pos[1][1] = 1.0-self.spacing/height
            pos[0] = pos[1] - self.zoom_size
            self.corrax[-1].set_position([pos[0][0], pos[0][1],
                                          self.zoom_size[0], self.zoom_size[1]])

    def make_selection(self, ax, key, x0, x1, y0, y1):
        if not key in ['shift', 'control']:
            self.mark_data = []
        try:
            axi = self.corrax.index(ax)
            # from scatter plots:
            c, r = self.corrindices[axi]
            if r < self.data.shape[1]:
                # from scatter:
                for ind, (x, y) in enumerate(zip(self.data[:,c], self.data[:,r])):
                    if x >= x0 and x <= x1 and y >= y0 and y <= y1:
                        if ind in self.mark_data:
                            if key == 'control':
                                self.mark_data.remove(ind)
                        else:
                            self.mark_data.append(ind)
            else:
                # from histogram:
                for ind, x in enumerate(self.data[:,c]):
                    if x >= x0 and x <= x1:
                        if ind in self.mark_data:
                            if key == 'control':
                                self.mark_data.remove(ind)
                        else:
                            self.mark_data.append(ind)
        except ValueError:
            try:
                r = self.histax.index(ax)
                # from histogram:
                for ind, x in enumerate(self.data[:,r]):
                    if x >= x0 and x <= x1:
                        if ind in self.mark_data:
                            if key == 'control':
                                self.mark_data.remove(ind)
                        else:
                            self.mark_data.append(ind)
            except ValueError:
                return
            
    def update_selection(self):
        # update scatter plots:
        for artist, (c, r) in zip(self.corrartists, self.corrindices):
            if artist is not None:
                artist.set_offsets(list(zip(self.data[self.mark_data,c],
                                            self.data[self.mark_data,r])))
                artist.set_facecolors(self.data_colors[self.mark_data])
        # waveform plot:
        if not self.wave_ax is None:
            self.wave_ax.clear()
            for idx in self.mark_data:
                if idx < len(self.waveform_data):
                    self.wave_ax.plot(self.waveform_data[idx][:,0],
                                      self.waveform_data[idx][:,1],
                                      c=self.data_colors[idx], lw=3, picker=5)
            self.fix_waveform_plot(self.wave_ax, self.mark_data)
        self.fig.canvas.draw()
        
    def on_key(self, event):
        #print('pressed', event.key)
        plot_zoom = True
        if event.key in ['left', 'right', 'up', 'down']:
            if self.zoomon:
                if event.key == 'left':
                    if self.corrindices[-1][0] > 0:
                        self.corrindices[-1][0] -= 1
                    else:
                        plot_zoom = False
                elif event.key == 'right':
                    if self.corrindices[-1][0] < self.corrindices[-1][1]-1 and \
                       self.corrindices[-1][0] < self.show_maxcols-1:
                        self.corrindices[-1][0] += 1
                    else:
                        plot_zoom = False
                elif event.key == 'up':
                    if self.corrindices[-1][1] > 1:
                        if self.corrindices[-1][1] >= self.data.shape[1]:
                            self.corrindices[-1][1] = self.show_maxcols-1
                        else:
                            self.corrindices[-1][1] -= 1
                        if self.corrindices[-1][0] >= self.corrindices[-1][1]:
                            self.corrindices[-1][0] = self.corrindices[-1][1]-1
                    else:
                        plot_zoom = False
                elif event.key == 'down':
                    if self.corrindices[-1][1] < self.show_maxcols:
                        self.corrindices[-1][1] += 1
                        if self.corrindices[-1][1] >= self.show_maxcols:
                            self.corrindices[-1][1] = self.data.shape[1]
                    else:
                        plot_zoom = False
        else:
            plot_zoom = False
            if event.key == 'escape':
                self.corrax[-1].set_position([0.5, 0.9, 0.05, 0.05])
                self.zoomon = False
                self.corrax[-1].set_visible(False)
                self.fig.canvas.draw()
            elif event.key in 'oz':
                self.select_zooms = not self.select_zooms
            elif event.key == 'backspace':
                if len(self.zoom_stack) > 0:
                    ax, xmin, xmax, ymin, ymax = self.zoom_stack.pop()
                    ax.set_xlim(xmin, xmax)
                    ax.set_ylim(ymin, ymax)
                    if ax in self.corrax[:-1]:
                        axidx = self.corrax[:-1].index(ax)
                        if self.corrindices[axidx][0] == self.corrindices[-1][0]:
                            self.corrax[-1].set_xlim(xmin, xmax)
                        if self.corrindices[axidx][1] == self.corrindices[-1][1]:
                            self.corrax[-1].set_ylim(ymin, ymax)
                    elif ax in self.histax:
                        if self.corrindices[-1][1] == self.data.shape[1] and \
                           self.corrindices[-1][0] == self.histax.index(ax):
                            self.corrax[-1].set_xlim(xmin, xmax)
                            self.corrax[-1].set_ylim(ymin, ymax)
                    self.fig.canvas.draw()
            elif event.key in '+=':
                self.pick_radius *= 1.5
            elif event.key in '-':
                if self.pick_radius > 5.0:
                    self.pick_radius /= 1.5
            elif event.key in '0':
                self.pick_radius = 4.0
            elif event.key in ['pageup', 'pagedown', '<', '>']:
                if event.key in ['pageup', '<'] and self.show_maxcols > 2:
                    self.show_maxcols -= 1
                elif event.key in ['pagedown', '>'] and self.show_maxcols < self.raw_data.shape[1]:
                    self.show_maxcols += 1
                self.update_layout()
            elif event.key in 'cC':
                if event.key in 'c':
                    self.color_index -= 1
                    if self.color_index < 0:
                        self.color_set_index -= 1
                        if self.color_set_index < -1:
                            self.color_set_index = len(self.all_data)-1
                        if self.color_set_index >= 0:
                            if self.all_data[self.color_set_index] is None:
                                self.compute_pca(self.color_set_index>1, True)
                            self.color_index = self.all_data[self.color_set_index].shape[1]-1
                        else:
                            self.color_index = 0 if self.extra_colors is None else 1
                else:
                    self.color_index += 1
                    if (self.color_set_index >= 0 and \
                        self.color_index >= self.all_data[self.color_set_index].shape[1]) or \
                        (self.color_set_index < 0 and \
                         self.color_index >= (1 if self.extra_colors is None else 2)):
                        self.color_index = 0
                        self.color_set_index += 1
                        if self.color_set_index >= len(self.all_data):
                            self.color_set_index = -1
                        elif self.all_data[self.color_set_index] is None:
                            self.compute_pca(self.color_set_index>1, True)
                self.set_color_column()
                for ax in self.corrax:
                    if len(ax.collections) > 0:
                        ax.collections[0].set_facecolors(self.data_colors)
                for a in self.corrartists:
                    if a is not None:
                        a.set_facecolors(self.data_colors[self.mark_data])
                if not self.wave_ax is None:
                    for l, c in zip(self.wave_ax.lines,
                                    self.data_colors[self.mark_data]):
                        l.set_color(c)
                self.plot_scatter(self.corrax[0], False, True, self.cbax)
                self.fix_scatter_plot(self.cbax, self.color_values,
                                      self.color_label, 'c')
                self.fig.canvas.draw()
            elif event.key in 'nN':
                if event.key in 'N':
                    self.hist_nbins = (self.hist_nbins*3)//2
                elif self.hist_nbins >= 15:
                    self.hist_nbins = (self.hist_nbins*2)//3
                for ax in self.histax:
                    self.plot_hist(ax, False, True)
                if self.corrindices[-1][1] >= self.data.shape[1]:
                    self.plot_hist(self.corrax[-1], True, True)
                elif not self.scatter:
                    self.plot_scatter(self.corrax[-1], True, True)
                if not self.scatter:
                    for ax in self.corrax[:-1]:
                        self.plot_scatter(ax, False, True)
                self.fig.canvas.draw()
            elif event.key in 'h':
                self.scatter = not self.scatter
                for ax in self.corrax[:-1]:
                    self.plot_scatter(ax, False, True)
                if self.corrindices[-1][1] < self.data.shape[1]:
                    self.plot_scatter(self.corrax[-1], True, True)
                self.fig.canvas.draw()
            elif event.key in 'pP':
                self.all_maxcols[self.show_mode] = self.show_maxcols
                if event.key == 'p':
                    self.show_mode += 1
                    if self.show_mode >= len(self.all_data):
                        self.show_mode = 0
                else:
                    self.show_mode -= 1
                    if self.show_mode < 0:
                        self.show_mode = len(self.all_data)-1
                if self.show_mode == 1:
                    print('PCA components')
                elif self.show_mode == 2:
                    print('scaled PCA components')
                else:
                    print('data')
                if self.all_data[self.show_mode] is None:
                    self.compute_pca(self.show_mode>1, True)
                self.data = self.all_data[self.show_mode]
                self.labels = self.all_labels[self.show_mode]
                self.show_maxcols = self.all_maxcols[self.show_mode]
                self.zoom_stack = []
                self.fig.canvas.set_window_title(self.title + ': ' + self.all_titles[self.show_mode])
                for ax in self.histax:
                    self.plot_hist(ax, False, False)
                for ax in self.corrax[:-1]:
                    self.plot_scatter(ax, False, False)
                self.update_layout()
            elif event.key in 'l':
                if len(self.mark_data) > 0:
                    print('')
                    print('selected:')
                    self.list_selection(self.mark_data)
        if plot_zoom:
            for k in reversed(range(len(self.zoom_stack))):
                if self.zoom_stack[k][0] == self.corrax[-1]:
                    del self.zoom_stack[k]
            self.corrax[-1].clear()
            self.corrax[-1].set_visible(True)
            self.zoomon = True
            self.set_zoom_pos(self.fig.get_window_extent().width,
                              self.fig.get_window_extent().height)
            if self.corrindices[-1][1] < self.data.shape[1]:
                self.plot_scatter(self.corrax[-1], True, False)
            else:
                self.plot_hist(self.corrax[-1], True, False)
            self.fig.canvas.draw()

    def on_select(self, eclick, erelease):
        if eclick.dblclick:
            if len(self.mark_data) > 0:
                self.analyze_selection(self.mark_data[-1])
            return
        x0 = min(eclick.xdata, erelease.xdata)
        x1 = max(eclick.xdata, erelease.xdata)
        y0 = min(eclick.ydata, erelease.ydata)
        y1 = max(eclick.ydata, erelease.ydata)
        ax = erelease.inaxes
        if ax is None:
            ax = eclick.inaxes
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()
        dx = 0.02*(xmax-xmin)
        dy = 0.02*(ymax-ymin)
        if x1 - x0 < dx and y1 - y0 < dy:
            bbox = ax.get_window_extent().transformed(self.fig.dpi_scale_trans.inverted())
            width, height = bbox.width, bbox.height
            width *= self.fig.dpi
            height *= self.fig.dpi
            dx = self.pick_radius*(xmax-xmin)/width
            dy = self.pick_radius*(ymax-ymin)/height
            x0 = erelease.xdata - dx
            x1 = erelease.xdata + dx
            y0 = erelease.ydata - dy
            y1 = erelease.ydata + dy
        elif self.select_zooms:
            self.zoom_stack.append((ax, xmin, xmax, ymin, ymax))
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
        self.make_selection(ax, erelease.key, x0, x1, y0, y1)
        self.update_selection()

    def on_pick(self, event):
        if not self.wave_ax is None:
            for k, l in enumerate(self.wave_ax.lines):
                if l is event.artist:
                    self.mark_data = [self.mark_data[k]]
        self.update_selection()
        if event.mouseevent.dblclick:
            if len(self.mark_data) > 0:
                self.analyze_selection(self.mark_data[-1])
            
    def set_layout(self, width, height):
        xoffs = self.xborder/width
        yoffs = self.yborder/height
        dx = (1.0-xoffs)/self.show_maxcols
        dy = (1.0-yoffs)/self.show_maxcols
        xs = self.spacing/width
        ys = self.spacing/height
        xw = dx - xs
        yw = dy - ys
        for c, ax in enumerate(self.histax):
            if c < self.show_maxcols:
                ax.set_position([xoffs+c*dx, yoffs, xw, yw])
                ax.set_visible(True)
            else:
                ax.set_visible(False)
                ax.set_position([0.99, 0.01, 0.01, 0.01])
        for ax, (c, r) in zip(self.corrax[:-1], self.corrindices[:-1]):
            if r < self.show_maxcols:
                ax.set_position([xoffs+c*dx, yoffs+(self.show_maxcols-r)*dy, xw, yw])
                ax.set_visible(True)
            else:
                ax.set_visible(False)
                ax.set_position([0.99, 0.01, 0.01, 0.01])
        self.cbax.set_position([xoffs+dx, yoffs+(self.show_maxcols-1)*dy, 0.3*xoffs, yw])
        self.set_zoom_pos(width, height)
        if self.zoom_back is not None:  # XXX Why is it sometimes None????
            bbox = self.corrax[-1].get_tightbbox(self.fig.canvas.get_renderer())
            if bbox is not None:
                self.zoom_back.set_bounds(bbox.x0, bbox.y0, bbox.width, bbox.height)
        x0 = xoffs+((self.show_maxcols+1)//2)*dx
        y0 = yoffs+((self.show_maxcols+1)//2)*dy
        if self.show_maxcols%2 == 0:
            x0 += xoffs
            y0 += yoffs
        if not self.wave_ax is None:
            self.wave_ax.set_position([x0, y0, 1.0-x0-xs, 1.0-y0-3*ys])

    def update_layout(self):
        if self.corrindices[-1][1] < self.data.shape[1]:
            if self.corrindices[-1][1] >= self.show_maxcols:
                self.corrindices[-1][1] = self.show_maxcols-1
            if self.corrindices[-1][0] >= self.corrindices[-1][1]:
                self.corrindices[-1][0] = self.corrindices[-1][1]-1
            self.plot_scatter(self.corrax[-1], True, False)
        else:
            if self.corrindices[-1][0] >= self.show_maxcols:
                self.corrindices[-1][0] = self.show_maxcols-1
                self.plot_hist(self.corrax[-1], True, False)
        self.set_layout(self.fig.get_window_extent().width,
                        self.fig.get_window_extent().height)
        self.fig.canvas.draw()

    def on_resize(self, event):
        self.set_layout(event.width, event.height)

            
class EODExplorer(MultivariateExplorer):
    
    def __init__(self, data, data_cols, wave_fish, eod_data,
                 rawdata_path, cfg):
        self.wave_fish = wave_fish
        self.eoddata = data
        self.path = rawdata_path
        MultivariateExplorer.__init__(self, 'EODExplorer', data[:,data_cols],
                                      None, eod_data)

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
        return np.min(data), np.max(data), None

    def fix_waveform_plot(self, ax, indices):
        if len(indices) == 0:
            self.wave_ax.text(0.5, 0.5, 'Click to plot EOD waveforms',
                              transform = self.wave_ax.transAxes,
                              ha='center', va='center')
            self.wave_ax.text(0.5, 0.3, 'n = %d' % len(self.raw_data),
                              transform = self.wave_ax.transAxes,
                              ha='center', va='center')
        elif len(indices) == 1:
            if 'index' in self.eoddata and \
              np.any(self.eoddata[:,'index'] != self.eoddata[0,'index']):
                ax.set_title('%s: %d' % (self.eoddata[indices[0],'file'],
                                         self.eoddata[indices[0],'index']))
            else:
                ax.set_title(self.eoddata[indices[0],'file'])
            ax.text(0.05, 0.85, '%.1fHz' % self.eoddata[indices[0],'EODf'],
                    transform = self.wave_ax.transAxes)
        else:
            ax.set_title('%d EOD waveforms selected' % len(indices))
        if self.wave_fish:
            ax.set_xlim(-0.7, 0.7)
            ax.set_xlabel('Time [1/EODf]')
            ax.set_ylim(-1.0, 1.0)
        else:
            ax.set_xlim(-0.5, 1.5)
            ax.set_xlabel('Time [ms]')
            ax.set_ylim(-1.5, 1.0)
        ax.set_ylabel('Amplitude')
    
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
        pulse_fish, psd_data, fishlist, eod_props, _, _, mean_eods, \
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
        print('left click              select data points')
        print('left and drag           rectangular selection and zoom of data points')
        print('shift + left click/drag add data points to selection')
        print('ctrl + left click/drag  add/remove data points to/from selection')
        print('')
        print('key shortcuts:')
        print('l                       list selected EOD waveforms on console')
        print('p,P                     toggle between data columns, PCA, and scaled PCA axis')
        print('<, pageup               decrease number of displayed data columns/PCA axis')
        print('>, pagedown             increase number of displayed data columns/PCA axis')
        print('o, z                    toggle zoom mode on or off')
        print('backspace               zoom back')
        print('+, -                    increase, decrease pick radius')
        print('0                       reset pick radius')
        print('n, N                    decrease, increase number of bins of histograms')
        print('h                       toggle between scatter plot and 2D histogram')
        print('c, C                    cycle color map trough data columns')
        print('left, right, up, down   show and move enlarged scatter plot')
        print('escape                  close enlarged scatter plot')
        parser.exit()      

        
wave_fish = True
data = None
data_path = None

def load_waveform(idx):
    eodf = data[idx,'EODf']
    file_name = data[idx,'file']
    file_index = data[idx,'index'] if 'index' in data else 0
    eod_table = TableData(os.path.join(data_path, '%s-eodwaveform-%d.csv' % (file_name, file_index)))
    eod = eod_table[:,'mean']
    if wave_fish:
        norm = max(np.max(eod), np.abs(np.min(eod)))
        return np.vstack((eod_table[:,'time']*0.001*eodf, eod/norm)).T
    else:
        norm = np.max(eod)
        return np.vstack((eod_table[:,'time'], eod/norm)).T

def main():
    global data
    global wave_fish
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
                        help='number of jobs run in parallel. Without argument use all CPU cores.')
    parser.add_argument('-D', dest='column_groups', default=[], type=str, action='append',
                        choices=['all', 'allpower', 'noise', 'timing', 'ampl', 'relampl', 'power', 'relpower', 'phase', 'time', 'width', 'none'],
                        help='default selection of data columns, check them with the -l option')
    parser.add_argument('-d', dest='add_data_cols', action='append', default=[], metavar='COLUMN',
                        help='data columns to be appended or removed (if already listed) for analysis')
    parser.add_argument('-n', dest='max_harmonics', default=0, type=int, metavar='MAX',
                        help='maximum number of harmonics or peaks to be used')
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

    # add cluster column (experimental):
    if wave_fish:
        # wavefish cluster:
        cluster = np.zeros(data.rows())
        cluster[(data[:,'phase1'] < 0) & (data[:,'EODf'] < 300.0)] = 1
        cluster[(data[:,'phase1'] < 0) & (data[:,'EODf'] > 300.0)] = 2
        cluster[data[:,'phase1'] > 0] = 3
        data.append('cluster', '', '%d', cluster)

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
    if jobs is not None:
        cpus = cpu_count() if jobs == 0 else jobs
        p = Pool(cpus)
        eod_data = p.map(load_waveform, range(data.rows()))
        del p
    else:
        eod_data = list(map(load_waveform, range(data.rows())))

    # explore:
    eod_expl = EODExplorer(data, data_cols, wave_fish, eod_data,
                          rawdata_path, cfg)
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
