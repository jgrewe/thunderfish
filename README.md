[![Build Status](https://travis-ci.org/bendalab/thunderfish.svg?branch=master)](https://travis-ci.org/bendalab/thunderfish)
[![Coverage Status](https://coveralls.io/repos/github/bendalab/thunderfish/badge.svg?branch=master)](https://coveralls.io/github/bendalab/thunderfish?branch=master)

# thunderfish

This repository is a collection of algorithms and programs for
analysing electric field recordings of weakly electric fish.

Weakly electric fish generate an electric organ discharge (EOD).  In
wave-type fish the EOD resembles a sinewave of a specific frequency
and with higher harmonics. In pulse-type fish EODs have a distinct
waveform and are separated in time.


## Software

The thunderfish package provides the following software:

- *fishfinder*: Browse EOD recordings and detect EOD frequencyies on the fly.
- *thunderfish*: Automatically detect and analyze all EOD waveforms in a short recording and generate a summary plot and data tables. [Read documentation](doc/thunderfish.md).
- *collectfish*: Collect data generated by thunderfish. [Read documentation](doc/collectfish.md).
- *eodexplorer*: View and explore properties of EOD waveforms. [Read documentation](doc/eodexplorer.md).


## Algorithms

The following modules provide the algorithms for analyzing EOD recordings.
Look into the modules for more information.

### Input/output

- *configfile.py*: Configuration file with help texts for analysis parameter.
- *consoleinput.py*: User input from console.
- *dataloader.py*: Load time-series data from files.
- *tabledata.py*: Read and write tables with a rich hierarchical header including units and formats.

### Basic data analysis

- *eventdetection.py*: Detect and hande peaks and troughs as well as threshold crossings in data arrays.
- *powerspectrum.py*: Compute and plot powerspectra and spectrograms for a given minimum frequency resolution.
- *voronoi.py*: Analyse Voronoi diagrams based on scipy.spatial.
- *multivariateexplorer.py*: Simple GUI for viewing and exploring multivariate data.

### EOD analysis

- *bestwindow.py*: Select the region within a recording with the most stable signal of largest amplitude that is not clipped.
- *checkpulse.py*: Check whether a pulse-type or a wave-type weakly electric fish is present in a recording.
- *consistentfishes.py*: Create a list of EOD frequencies with fishes present in all provided fish lists.
- *eodanalysis.py*: Analyse EOD waveforms.
- *harmonics.py*: Extract and analyze harmonic frequencies from power spectra.

### EOD simulations
- *fakefish.py*: Generate artificial EOD waveforms and fields.
- *fishshapes.py*: Plot fish silhouettes.



