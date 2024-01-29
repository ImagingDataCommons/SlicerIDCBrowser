# This 3D Slicer module allows launching 3D Slicer from the web browser and load NRRD file.
# It uses a custom URL, which launches 3D Slicer and contains the download URL as query parameter (with percent encoding).
# See discussion at https://discourse.slicer.org/t/how-to-load-nifti-file-from-web-browser-link/18664/5

#
# Setup:
# - save this file as "LoadRemoteFile.py" in an empty folder.
# - add the folder to additional module paths in Slicer
#
# To test, open a terminal and execute this command:
#
# start slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd
#

import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


import pkg_resources
from urllib.request import urlopen
import json
from packaging import version

from idc_index import index

idc_client = index.IDCClient()


def is_module_installed(module_name):
    """
    This function checks if a Python package is installed.

    Parameters:
    module_name (str): The name of the module to check.

    Returns:
    bool: True if the module is installed, False otherwise.
    """
    try:
        pkg_resources.get_distribution(module_name)
        return True
    except pkg_resources.DistributionNotFound:
        return False

package_name='idc-index'
"""
Check if idc-index Python package is installed and install or update it 

"""
if is_module_installed(package_name):
    print(package_name + " is installed")

    # Check if the package is outdated
    installed_version = version.parse(pkg_resources.get_distribution(package_name).version)
    available_version = None

    try:
        response = urlopen(f'https://pypi.org/pypi/{package_name}/json')
        data = json.loads(response.read())
        available_version = version.parse(data['info']['version'])
    except Exception as e:
        print(f"Error fetching available version: {e}")

    if available_version and installed_version < available_version:
        print(package_name + " is outdated")
        slicer.util.pip_install(package_name)
    else:
        print(package_name + " is up-to-date")
else:
    print(package_name + " is not installed")

#
# ViewIDCData
#

class ViewIDCData(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "View IDC Data"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["IDC"]
    self.parent.helpText = """

"""
    self.parent.acknowledgementText = """
This file was inspired by the original file written by Andras Lasso, PerkLab and ASH.
The original file can be found in the discussion.
https://discourse.slicer.org/t/how-to-load-nifti-file-from-web-browser-link/18664/5
"""

    # Initilize self.sampleDataLogic. At this point, Slicer modules are not initialized yet, so we cannot instantiate the logic yet.
    self.sampleDataLogic = None

    slicer.app.connect("urlReceived(QString)", self.onURLReceived)

  def reportProgress(self, message, logLevel=None):
    # Print progress in the console
    print(f"Loading... {self.sampleDataLogic.downloadPercent}%")
    # Abort download if cancel is clicked in progress bar
    if self.progressWindow.wasCanceled:
        raise Exception("download aborted")
    # Update progress window
    self.progressWindow.show()
    self.progressWindow.activateWindow()
    self.progressWindow.setValue(int(self.sampleDataLogic.downloadPercent))
    self.progressWindow.setLabelText("Downloading...")
    # Process events to allow screen to refresh
    slicer.app.processEvents()

  def center3dViews(self):
    layoutManager = slicer.app.layoutManager()
    for threeDViewIndex in range(layoutManager.threeDViewCount):
      threeDWidget = layoutManager.threeDWidget(0)
      threeDView = threeDWidget.threeDView()
      threeDView.resetFocalPoint()

  def showSliceViewsIn3d(self):
    layoutManager = slicer.app.layoutManager()
    for sliceViewName in layoutManager.sliceViewNames():
      controller = layoutManager.sliceWidget(sliceViewName).sliceController()
      controller.setSliceVisible(True)

  def onURLReceived(self, urlString):
    """Process DICOM view requests. URL protocol and path must be: slicer://viewer/
    Query parameters:
      - `download`: download and show with default file type
      - `image` or `volume`: download and show as image
      - `segmentation`: download and show as segmentation
      - `show3d`: show segmentation in 3D and center 3D view
      - `filename`: filename to specify file format and node name for the first node; useful if the download URL does not contain filename

    Display a file (using default file type):

        slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

    Display a segmentation and volume file:

        slicer://viewer/?show3d=true&segmentation=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerMaskSegmentation.seg.nrrd&image=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

    """
    logging.info(f"URL received: {urlString}")

    # Check if we understand this URL
    url = qt.QUrl(urlString)
    if url.authority().lower() != "idcbrowser":
        return
    query = qt.QUrlQuery(url)

    # Parse options
    queryMap = {}
    for key, value in query.queryItems(qt.QUrl.FullyDecoded):
        queryMap[key] = value

    # Get list of files to load
    filesToOpen = []
    for nodeIndex, [key, value] in enumerate(query.queryItems(qt.QUrl.FullyDecoded)):
      if key == "download":
        fileType = None
      elif key == "image" or key == "volume":
        fileType = "VolumeFile"
      elif key == "segmentation":
        fileType = "SegmentationFile"
      else:
        continue
      downloadUrl = qt.QUrl(value)

       # Get the node name from URL
      if (nodeIndex == 0) and ("filename" in queryMap):
        baseName = queryMap["filename"]
      else:
        baseName = os.path.basename(downloadUrl.path())

      nodeName, ext = os.path.splitext(baseName)
      # Generate random filename to avoid reusing/overwriting older downloaded files that may have the same name
      import uuid
      fileName = f"{nodeName}-{uuid.uuid4().hex}{ext}"
      info = {"downloadUrl": downloadUrl, "nodeName": nodeName, "fileName": fileName, "fileType": fileType}
      filesToOpen.append(info)

    if not filesToOpen:
        return

    show3d = False
    if "show3d" in queryMap:
      print("Show 3d")
      show3d = slicer.util.toBool(queryMap["show3d"])

    # Ensure sampleData logic is created
    if not self.sampleDataLogic:
      import SampleData
      self.sampleDataLogic = SampleData.SampleDataLogic()

    for info in filesToOpen:
      downloadUrlString = info["downloadUrl"].toString()
      logging.info(f"Download URL detected - get the file from {downloadUrlString} and load it now")
      try:
          self.progressWindow = slicer.util.createProgressDialog()
          self.sampleDataLogic.logMessage = self.reportProgress

          #loadedNodes = self.sampleDataLogic.downloadFromURL(nodeNames=info["nodeName"], fileNames=info["fileName"], uris=downloadUrlString, loadFileTypes=info["fileType"])
          
          destFolderPath = slicer.mrmlScene.GetCacheManager().GetRemoteCacheDirectory()
          seriesInstanceUID=str(downloadUrl)

          # Create a new folder named with 'seriesInstanceUID' in 'destFolderPath'
          download_folder_path = os.path.join(destFolderPath, str(seriesInstanceUID))

          print("seriesInstanceUID: "+seriesInstanceUID)
          print("destFolderPath "+download_folder_path)

          # Download the DICOM series to the new folder
          idc_client.download_dicom_series(seriesInstanceUID=seriesInstanceUID, downloadDir=download_folder_path)

          indexer = ctk.ctkDICOMIndexer()
          indexer.addDirectory(slicer.dicomDatabase, download_folder_path)

          plugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
          seriesUID = seriesInstanceUID.replace("'", "")
          dicomDatabase = slicer.dicomDatabase
          fileList = slicer.dicomDatabase.filesForSeries(seriesUID)
          loadables = plugin.examine([fileList])
          if len(loadables)>0:
            volume = plugin.load(loadables[0])
            logging.debug("Loaded volume: " + volume.GetName())
          else:
            self.showStatus("Unable to load DICOM content. Please retry from DICOM Browser!")

          # remove downloaded file
          #os.remove(slicer.app.cachePath + "/" + info["fileName"])

          #if show3d:
          #  for loadedNode in loadedNodes:
          #    if type(loadedNode) == slicer.vtkMRMLSegmentationNode:
                # Show segmentation in 3D
          #      loadedNode.CreateClosedSurfaceRepresentation()
              # elif type(loadedNode) == slicer.vtkMRMLVolumeNode:
              #   # Show volume rendering in 3D
              #   pluginHandler = slicer.qSlicerSubjectHierarchyPluginHandler().instance()
              #   vrPlugin = pluginHandler.pluginByName("VolumeRendering")
              #   volumeItem = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene).GetItemByDataNode(loadedNode)
              #   vrPlugin.setDisplayVisibility(volumeItem, True)
              #   vrPlugin.showVolumeRendering(True, volumeItem)
      finally:
          self.progressWindow.close()

    if show3d:
      self.center3dViews()
      self.showSliceViewsIn3d()


  # def setups5cmd(self):
  #   print("setups5cmd")
  #   self.finds5cmd()
  #   if not self.iss5cmdPathValid():
  #       # s5cmd not found, offer downloading it
  #       if slicer.util.confirmOkCancelDisplay(
  #           's5cmd download tool is not detected on your system. '
  #           'Download s5cmd?',
  #               windowTitle='Download confirmation'):
  #           if not self.s5cmdDownload():
  #               slicer.util.errorDisplay("s5cmd download failed")
  #   if not self.iss5cmdPathValid():
  #       return False
  #   return True