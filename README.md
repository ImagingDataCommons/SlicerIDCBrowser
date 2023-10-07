3D Slicer IDC Browser extension
===========

![logo](https://github.com/ImagingDataCommons/SlicerIDCBrowser/blob/c9519809522aaac59bb65fb558b1197cf05c3e72/IDCBrowser/Resources/Icons/IDCBrowser.png?raw=true)


## About
IDCBrowser is a [3D Slicer](http://slicer.org/) extension for browsing and downloading DICOM files from [NCI Imaging Data Commons](https://imaging.datacommons.cancer.gov/).

Development of this extension was [initiated](https://projectweek.na-mic.org/PW39_2023_Montreal/Projects/SlicerIDCBrowser/) in June 2023. As of October 7, 2023, the extension should be available in the 3D Slicer 5.5.0 preview and 5.4.0 stable releases.

## Usage

You can install the extension via 3D Slicer [Extensions Manager](https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html). 

Once the extension is installed, it provides interface to choose from any of the imaging collections available in Imaging Data Commons, and select and download imaging data at the patient, study or series level. 

This extension relies on [`s5cmd`](https://github.com/peak/s5cmd) command line tool, which is installed by the extension, and is used to download images stored in DICOM format from the cloud-based storage buckets maintained by the IDC team.

**WARNING**: the extension is in its early stages, with the interface and features expected to evolve.

## Development

See current status of the extension builds in the 3D Slicer Preview dashboard [here](https://slicer.cdash.org/index.php?project=SlicerPreview&filtercount=1&showfilters=1&field1=buildname&compare1=63&value1=idcbrowser).

## Acknowledgments

This project has been funded in whole or in part with Federal funds from the National Cancer Institute, National Institutes of Health, under Task Order No. HHSN26110071 under Contract No. HHSN261201500003l.

The overview of IDC is available in this open access publication. If you use IDC, please acknowledge us by citing it!

> Fedorov, A., Longabaugh, W. J. R., Pot, D., Clunie, D. A., Pieper, S., Aerts, H. J. W. L., Homeyer, A., Lewis, R., Akbarzadeh, A., Bontempi, D., Clifford, W., Herrmann, M. D., Höfener, H., Octaviano, I., Osborne, C., Paquette, S., Petts, J., Punzo, D., Reyes, M., Schacherer, D. P., Tian, M., White, G., Ziegler, E., Shmulevich, I., Pihl, T., Wagner, U., Farahani, K. & Kikinis, R. NCI Imaging Data Commons. Cancer Res. 81, 4188–4193 (2021). http://dx.doi.org/10.1158/0008-5472.CAN-21-0950
