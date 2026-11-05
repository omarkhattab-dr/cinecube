# data

l1448_13co.fits (2.3 MB) - L1448 in 13CO 1-0, FCRAO COMPLETE survey (Ridge et al 2006), copied from the
astropy-data repo (github.com/astropy/astropy-data, l1448/l1448_13co.fits). 105x105 px, 53 channels,
0.066 km/s per channel, noise ~0.24 K. no beam in the header, 46 arcsec / 23 arcsec px = 2 px (yaml).

exoalma_j1615_12co.fits (33.6 MB) - J1615-3255 protoplanetary disk in 12CO 3-2 (not 2-1, exoALMA is band 7),
ALMA, exoALMA fiducial line image (Teague et al 2025 exoALMA I, Loomis et al 2025 exoALMA II), harvard
dataverse doi:10.7910/DVN/CFHWNH file 11120493, CC0. the original is 1024x1024x301 Jy/beam with a FREQ axis,
cinecube.prep cropped the middle 256x256 px (0.025 arcsec px, no resampling) and 128 channels around the
line, converted Jy/beam -> K through the beam and FREQ -> km/s (radio, RESTFRQ 345.796 GHz). beam 0.15
arcsec = 6 px from the header, 0.1 km/s channels, noise ~1.35 K. everything it did is in
exoalma_j1615_12co_prep.json. cite exoALMA I + II if the cube shows up anywhere.

synthetic_disk.fits + synthetic_disk_truth.npz are not committed, make disk builds them in a few sec.
