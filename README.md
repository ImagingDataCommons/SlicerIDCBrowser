3D Slicer IDC Browser extension
===========

![logo](https://github.com/ImagingDataCommons/SlicerIDCBrowser/blob/c9519809522aaac59bb65fb558b1197cf05c3e72/IDCBrowser/Resources/Icons/IDCBrowser.png?raw=true)


## About
IDCBrowser is a [3D Slicer](http://slicer.org/) extension for browsing and downloading DICOM files from [NCI Imaging Data Commons](https://imaging.datacommons.cancer.gov/).

Development of this extension was [initiated](https://projectweek.na-mic.org/PW39_2023_Montreal/Projects/SlicerIDCBrowser/) in June 2023. As of October 7, 2023, the extension should be available in the 3D Slicer 5.5.0 preview and 5.4.0 stable releases.

## Installation

You can install the extension via 3D Slicer [Extensions Manager](https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html). 

Once the extension is installed, it provides interface to choose from any of the imaging collections available in Imaging Data Commons, and select and download imaging data at the patient, study or series level. 

This extension relies on [`s5cmd`](https://github.com/peak/s5cmd) command line tool, which is installed by the extension, and is used to download images stored in DICOM format from the cloud-based storage buckets maintained by the IDC team.

**WARNING**: the extension is in its early stages, with the interface and features expected to evolve.

## View IDC data in a locally installed Slicer Instance

## 👷‍♂️🚧 **WARNING**: this feature is in its early development stages. Its functionality may change. Stay tuned for the updates and documentation, and please share your feedback about it by opening issues in this repository🚧

Viewing IDC Data directly in Slicer is one of the features we are planning to bring and is still in development stages

### Steps to try out this feature: 
1. Git clone this repo.
```bash
git clone https://github.com/ImagingDataCommons/SlicerIDCBrowser.git
```
2. Checkout add-slicer-idc-viewer branch (eventually this feature will be available on main branch)
```bash
cd SlicerIDCBrowser
git checkout add-slicer-idc-viewer
```

3. Add the `src` folder as one of the module paths in Slicer settings. Refer to the screenshot below for more information:
   
![Screenshot (17)](https://github.com/vkt1414/slicer-idc-viewer/assets/115020590/48b5a945-3d81-45f8-b7e5-9b1e9f1024e9)

![Screenshot (18)](https://github.com/vkt1414/slicer-idc-viewer/assets/115020590/6136b1de-b117-4b04-b961-57cf14f0a4e9)

![Screenshot (19)](https://github.com/vkt1414/slicer-idc-viewer/assets/115020590/157d50c9-6224-4984-8b94-714a76b86a20)

![Screenshot (20)](https://github.com/vkt1414/slicer-idc-viewer/assets/115020590/666a5513-72c0-43af-80eb-ece9dab0cf76)

4. Restart Slicer
5. Open a URL like `slicer://idc-browser/?download=$seriesinstanceuid` for example
   ```
   slicer://idc-browser/?download=1.2.840.113654.2.55.154809705591242159075253605419469935510
   ```

## Development

See current status of the extension builds in the 3D Slicer Preview dashboard [here](https://slicer.cdash.org/index.php?project=SlicerPreview&filtercount=1&showfilters=1&field1=buildname&compare1=63&value1=idcbrowser).


## Acknowledgments

This project has been funded in whole or in part with Federal funds from the National Cancer Institute, National Institutes of Health, under Task Order No. HHSN26110071 under Contract No. HHSN261201500003l.

The overview of IDC is available in this open access publication. If you use IDC, please acknowledge us by citing it!

> Fedorov, A., Longabaugh, W. J. R., Pot, D., Clunie, D. A., Pieper, S., Aerts, H. J. W. L., Homeyer, A., Lewis, R., Akbarzadeh, A., Bontempi, D., Clifford, W., Herrmann, M. D., Höfener, H., Octaviano, I., Osborne, C., Paquette, S., Petts, J., Punzo, D., Reyes, M., Schacherer, D. P., Tian, M., White, G., Ziegler, E., Shmulevich, I., Pihl, T., Wagner, U., Farahani, K. & Kikinis, R. NCI Imaging Data Commons. Cancer Res. 81, 4188–4193 (2021). http://dx.doi.org/10.1158/0008-5472.CAN-21-0950
