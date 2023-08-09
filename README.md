# heo-xas-xrd
Code for processing and plotting of data from XAS and XRD studies performed at SOLEIL/ROCK and ESRF/BM23. Detailed usage instructions are available but not here.

# Files
### `OLD-xas-compare-pca`
Uses a deprecated naive method for data normalization. Should never be used. See `xas-pca-compare`.

### `fdmgen` and `fdmgen-config`
Simple script for batch-producing FDMNES input files that reference a CIF structure directly. To be run from the same directory in which the `fdmfile` should be produced.

### `materials-project-query`
A failed attempt at custom queries to the Materials Project database using the new `mp-api`.

### `nexus-read`
An example of reading `.nxs` data. Not used in practice.

### `struct2xas-client`
Client notebook to produce FDMNES input files from CIF structures, including visualization and other quality-of-life features owing to `struct2xas`.

### `struct2xas`
A version of bfoschiani's `struct2xas` I use. Currently has some issues with certain structures.

### `xas-pca-compare`
Intended to take inconveniently large sets of normalized XAS data and cluster the spectra based on their principle component decompositions with no manual intervention.

### `xas-pca-time-evolution`
See `xas-pca-compare`, also includes ability to plot timeseries tracking evolution of XAS spectra through the space of XAS data. Will become useful once time-resolved XAS are available, in addition to steady-state references. Currently tested on time-resolved XANES data, with mediocre results.

### `xas-time-evolution-bm23`
For plotting XAS over time and temperature, as well as spectrograms of change over time, and integrated change over time (difference spectra). Works with ESRF beamline HDF5 files.

### `xas-time-evolution-rock`
Same as `xas-time-evolution-bm23` but includes code to read the specific directory structure produced by the ROCK beamline at SOLEIL when operated in quick-EXAFS mode and processed using `moulinex` and whatever other dark magic they have over there.

### `rocklogparse`
Fragile code hacked together for parsing log files made in human-readable formats.

### `xrd-batch-integrate`
Uses geometry (PONI) data acquired through calibration images (`xrd-cal`) to perform azimuthal integration on XRD patterns from area detectors.

### `xrd-cal`
Client to `pyfai` for calibration of area detectors.

### `xrd-sim`
Work in progress for producing fake images of XRD patterns given geometry and sample data.

### `xrd-time-evolution`
Used to plot azimuthally integrated XRD patterns over time and temperature.
