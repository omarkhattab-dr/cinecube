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

things_ngc2403_hi.fits (36 MB) - NGC 2403 in HI 21 cm, VLA, THINGS natural weighted cube (Walter et al 2008,
AJ 136, 2563), from things.www3.mpia.de Data_files/NGC_2403_NA_CUBE_THINGS.FITS (the old www2.mpia-hd.mpg.de
address redirects there). original 2048x2048x61 JY/BEAM, 1 arcsec px, FELO-HEL (optical velocity) axis, a
stokes axis, beam 8.75x7.65 arcsec in the AIPS HISTORY line. cinecube.prep: 4x4 block mean (4 arcsec px),
384x384 (25.6 arcmin, the whole galaxy, 256 would cut it), all 61 channels (5.16 km/s each), Jy/beam -> K
through the beam, velocity -> km/s. beam 2.19 px from the header. noise ~2.9 K per channel. no NaN padding.
things_ngc2403_hi_prep.json has the details.
