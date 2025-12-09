# Future imports
from __future__ import division

# Standard library imports
import codecs
import csv
import json
import logging
import os.path
import pickle
import string
import sys
import time
import unittest
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from random import randint
import tempfile
import inspect

# Third-party imports
import pydicom
import pkg_resources
import qt
import urllib

#slicer
from __main__ import vtk, qt, ctk, slicer

# Local application imports
from slicer.ScriptedLoadableModule import *

#
# IDCBrowser
#

class IDCBrowser(ScriptedLoadableModule):
  def __init__(self, parent):

    ScriptedLoadableModule.__init__(self, parent)

    parent.title = "SlicerIDCBrowser"
    parent.categories = ["Informatics"]
    parent.dependencies = []
    parent.contributors = ["Andrey Fedorov (SPL, BWH)"]
    parent.helpText = """ Explore the content of NCI Imaging Data Commons and download DICOM data into 3D Slicer. See <a href=\"https://github.com/ImagingDataCommons/SlicerIDCBrowser\">
    the documentation</a> for more information. This project has been funded in whole or in part with Federal funds from the National Cancer Institute, National Institutes of Health, under Task Order No. HHSN26110071 under Contract No. HHSN261201500003l.
    """



#
# qIDCBrowserWidget
#

class IDCBrowserWidget(ScriptedLoadableModuleWidget):

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load settings from the system
    self.settings = qt.QSettings()

    self.loadToScene = False

    # This module is often used in developer mode, therefore
    # collapse reload & test section by default.
    if hasattr(self, "reloadCollapsibleButton"):
        self.reloadCollapsibleButton.collapsed = True

    self.logic = IDCBrowserLogic()

    # Get module path for resources
    if 'IDCBrowser' in slicer.util.moduleNames():
      self.modulePath = slicer.modules.idcbrowser.path.replace("IDCBrowser.py", "")
    else:
      self.modulePath = '.'

    logging.info("Checking requirements ...")
    update = slicer.util.settingsValue("IDCBrowser/PipUpdateRequested", False, converter=slicer.util.toBool)
    if self.logic.setupPythonRequirements(update):
      self.settings.setValue("IDCBrowser/PipUpdateRequested", False)

    from idc_index import index

    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

    logging.info("Initializing IDC client ...")
    startTime = time.time()
    self.IDCClient = index.IDCClient()
    logging.info("IDC Client initialized in {0:.2f} seconds.".format(time.time() - startTime))
    qt.QApplication.restoreOverrideCursor()

    logging.debug("s5cmd path: " + self.IDCClient.s5cmdPath)

    self.IDCClient.IDCIndexPath = self.logic.getIDCIndexPath()
    logging.debug("IDCIndex path: " + self.IDCClient.IDCIndexPath)

    logging.info("Initialization done.")

    # Load the browser widget UI
    uiFilePath = os.path.join(self.modulePath, 'Resources', 'UI', 'IDCBrowserMain.ui')
    self.browserWidget = slicer.util.loadUI(uiFilePath)
    self.browserWidget.setObjectName("browserWidget")
    self.browserWidget.setWindowTitle('SlicerIDCBrowser | NCI Imaging Data Commons data release '+self.logic.idc_version)

    self.initialConnection = False
    self.seriesTableRowCount = 0
    self.studiesTableRowCount = 0
    self.downloadProgressLabels = {}
    self.selectedSeriesNicknamesDic = {}
    self.downloadQueue = {}
    self.seriesRowNumber = {}

    self.imagesToDownloadCount = 0

    # Create a timer for debounced search
    self.searchDebounceTimer = qt.QTimer()
    self.searchDebounceTimer.setSingleShot(True)
    self.searchDebounceTimer.setInterval(300)
    self.searchDebounceTimer.timeout.connect(self.performUnifiedSearch)

    # Flag to track if we're searching specifically for a series (to prevent auto-select all)
    self.isSearchingForSpecificSeries = False

    item = qt.QStandardItem()

    # Put the files downloaded from IDC in the DICOM database folder by default.
    # This makes downloaded files relocatable along with the DICOM database in
    # recent Slicer versions.

    dicomDatabase = slicer.app.dicomDatabase()
    if not os.path.isfile(dicomDatabase.databaseFilename):
      dicomBrowser = ctk.ctkDICOMBrowser()
      dicomBrowser.databaseDirectory = dicomDatabase.databaseDirectory
      dicomBrowser.createNewDatabaseDirectory()
      dicomDatabase.openDatabase(dicomDatabase.databaseFilename)
      logging.info("DICOM database created")
    else:
      logging.info('DICOM database is available at '+dicomDatabase.databaseFilename)
      dicomDatabase.updateSchemaIfNeeded()

    databaseDirectory = dicomDatabase.databaseDirectory
    self.storagePath = self.settings.value("IDCCustomStoragePath")  if self.settings.contains("IDCCustomStoragePath") else databaseDirectory + "/IDCLocal/"
    logging.debug("IDC downloaded data storage path: " + self.storagePath)
    if not os.path.exists(self.storagePath):
      os.makedirs(self.storagePath)
    if not self.settings.contains("IDCDefaultStoragePath"):
      self.settings.setValue("IDCDefaultStoragePath", (databaseDirectory + "/IDCLocal/"))

    self.cachePath = self.storagePath + "/ServerResponseCache/"
    logging.debug("IDC cache path: " + self.cachePath)
    self.downloadedSeriesArchiveFile = self.storagePath + 'archive.p'
    if os.path.isfile(self.downloadedSeriesArchiveFile):
      print("Reading "+self.downloadedSeriesArchiveFile)
      f = open(self.downloadedSeriesArchiveFile, 'rb')
      self.previouslyDownloadedSeries = pickle.load(f)
      f.close()
    else:
      with open(self.downloadedSeriesArchiveFile, 'wb') as f:
        self.previouslyDownloadedSeries = []
        pickle.dump(self.previouslyDownloadedSeries, f)
      f.close()

    if not os.path.exists(self.cachePath):
      os.makedirs(self.cachePath)
    self.useCacheFlag = False

    # Load icons
    self.reportIcon = qt.QIcon(self.modulePath + '/Resources/Icons/report.png')
    downloadAndIndexIcon = qt.QIcon(self.modulePath + '/Resources/Icons/downloadAndIndex.png')
    downloadAndLoadIcon = qt.QIcon(self.modulePath + '/Resources/Icons/downloadAndLoad.png')
    browserIcon = qt.QIcon(self.modulePath + '/Resources/Icons/IDCBrowser.png')
    cancelIcon = qt.QIcon(self.modulePath + '/Resources/Icons/cancel.png')
    self.downloadIcon = qt.QIcon(self.modulePath + '/Resources/Icons/download.png')
    self.storedlIcon = qt.QIcon(self.modulePath + '/Resources/Icons/stored.png')
    self.browserWidget.setWindowIcon(browserIcon)

    #
    # Reload and Test area
    #
    reloadCollapsibleButton = ctk.ctkCollapsibleButton()
    reloadCollapsibleButton.text = "Reload && Test"
    # uncomment the next line for developing and testing
    # self.layout.addWidget(reloadCollapsibleButton)
    reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)

    # reload button
    # (use this during development, but remove it when delivering
    #  your module to users)
    self.reloadButton = qt.QPushButton("Reload")
    self.reloadButton.toolTip = "Reload this module."
    self.reloadButton.name = "IDCBrowser Reload"
    reloadFormLayout.addWidget(self.reloadButton)
    self.reloadButton.connect('clicked()', self.onReload)

    # reload and test button
    # (use this during development, but remove it when delivering
    #  your module to users)
    self.reloadAndTestButton = qt.QPushButton("Reload and Test")
    self.reloadAndTestButton.toolTip = "Reload this module and then run the self tests."
    reloadFormLayout.addWidget(self.reloadAndTestButton)
    self.reloadAndTestButton.connect('clicked()', self.onReloadAndTest)

    # Load the module panel UI
    uiFilePath = os.path.join(self.modulePath, 'Resources', 'UI', 'IDCBrowser.ui')
    self.ui = slicer.util.loadUI(uiFilePath)
    self.layout.addWidget(self.ui)

    # Get references to UI widgets from the loaded panel
    self.updateRequiredWidget = self.ui.findChild(qt.QWidget, "updateRequiredWidget")
    self.updateRequiredLabel = self.ui.findChild(qt.QLabel, "updateRequiredLabel")
    self.updateAndRestartButton = self.ui.findChild(qt.QPushButton, "updateAndRestartButton")
    self.browserCollapsibleButton = self.ui.findChild(ctk.ctkCollapsibleButton, "browserCollapsibleButton")
    self.showBrowserButton = self.ui.findChild(qt.QPushButton, "showBrowserButton")
    self.downloadDestinationSelector = self.ui.findChild(ctk.ctkDirectoryButton, "downloadDestinationSelector")
    self.manifestSelector = self.ui.findChild(ctk.ctkPathLineEdit, "manifestSelector")
    self.downloadProgressBar = self.ui.findChild(qt.QProgressBar, "downloadProgressBar")
    self.storagePathButton = self.ui.findChild(ctk.ctkDirectoryButton, "storagePathButton")
    self.storageResetButton = self.ui.findChild(qt.QPushButton, "storageResetButton")
    self.webWidgetCheckBox = self.ui.findChild(qt.QCheckBox, "webWidgetCheckBox")

    # Update widgets with dynamic content
    self.browserCollapsibleButton.text = "SlicerIDCBrowser | NCI Imaging Data Commons data release " + self.logic.idc_version
    self.updateAndRestartButton.connect('clicked(bool)', slicer.util.restart)
    self.updateUpgradeRequiredWidget()

    # Get references to browser widget UI elements
    self.unifiedSearchSelector = self.browserWidget.findChild(ctk.ctkSearchBox, "unifiedSearchSelector")
    self.searchWarningLabel = self.browserWidget.findChild(qt.QLabel, "searchWarningLabel")
    self.collectionsCollapsibleGroupBox = self.browserWidget.findChild(ctk.ctkCollapsibleGroupBox, "collectionsCollapsibleGroupBox")
    self.collectionSelectorLabel = self.browserWidget.findChild(qt.QLabel, "collectionSelectorLabel")
    self.collectionSelector = self.browserWidget.findChild(qt.QComboBox, "collectionSelector")
    self.logoLabel = self.browserWidget.findChild(qt.QLabel, "logoLabel")
    self.patientsCollapsibleGroupBox = self.browserWidget.findChild(ctk.ctkCollapsibleGroupBox, "patientsCollapsibleGroupBox")
    self.patientsTableWidget = self.browserWidget.findChild(qt.QTableWidget, "patientsTableWidget")
    self.studiesCollapsibleGroupBox = self.browserWidget.findChild(ctk.ctkCollapsibleGroupBox, "studiesCollapsibleGroupBox")
    self.studiesTableWidget = self.browserWidget.findChild(qt.QTableWidget, "studiesTableWidget")
    self.studiesSelectAllButton = self.browserWidget.findChild(qt.QPushButton, "studiesSelectAllButton")
    self.studiesSelectNoneButton = self.browserWidget.findChild(qt.QPushButton, "studiesSelectNoneButton")
    self.seriesCollapsibleGroupBox = self.browserWidget.findChild(ctk.ctkCollapsibleGroupBox, "seriesCollapsibleGroupBox")
    self.seriesTableWidget = self.browserWidget.findChild(qt.QTableWidget, "seriesTableWidget")
    self.seriesSelectAllButton = self.browserWidget.findChild(qt.QPushButton, "seriesSelectAllButton")
    self.seriesSelectNoneButton = self.browserWidget.findChild(qt.QPushButton, "seriesSelectNoneButton")
    self.imagesCountLabel = self.browserWidget.findChild(qt.QLabel, "imagesCountLabel")
    self.indexButton = self.browserWidget.findChild(qt.QPushButton, "indexButton")
    self.loadButton = self.browserWidget.findChild(qt.QPushButton, "loadButton")
    self.cancelDownloadButton = self.browserWidget.findChild(qt.QPushButton, "cancelDownloadButton")
    self.statusFrame = self.browserWidget.findChild(qt.QFrame, "statusFrame")
    self.statusLabel = self.browserWidget.findChild(qt.QLabel, "statusLabel")

    # Set up geometry for browser widget
    self.popupGeometry = qt.QRect()
    settings = qt.QSettings()
    mainWindow = slicer.util.mainWindow()
    if mainWindow:
      width = mainWindow.width * 0.75
      height = mainWindow.height * 0.75
      self.popupGeometry.setWidth(width)
      self.popupGeometry.setHeight(height)
      self.popupPositioned = False
      self.browserWidget.setGeometry(self.popupGeometry)

    # Set up QCompleter for auto-completion
    self.collectionCompleter = qt.QCompleter()
    self.collectionCompleter.setCaseSensitivity(qt.Qt.CaseInsensitive)
    self.collectionCompleter.setCompletionMode(qt.QCompleter.PopupCompletion)
    self.collectionCompleter.setFilterMode(qt.Qt.MatchContains)
    self.collectionCompleter.setModel(qt.QStringListModel())
    self.collectionSelector.setCompleter(self.collectionCompleter)

    # Update logo label with IDC version
    logoLabelText = "IDC release "+self.logic.idc_version
    self.logoLabel.text = logoLabelText

    # Set download destination
    self.downloadDestinationSelector.directory = self.storagePath

    # Configure table widgets
    self.patientsModel = qt.QStandardItemModel()
    self.patientsTableHeaderLabels = ['Patient ID', 'Patient Sex', 'Patient Age']
    self.patientsTableWidgetHeader = self.patientsTableWidget.horizontalHeader()
    self.patientsTreeSelectionModel = self.patientsTableWidget.selectionModel()
    abstractItemView = qt.QAbstractItemView()
    self.patientsTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    verticalheader = self.patientsTableWidget.verticalHeader()
    verticalheader.setDefaultSectionSize(20)

    self.studiesModel = qt.QStandardItemModel()
    self.studiesTableHeaderLabels = ['Study Instance UID', 'Study Date', 'Study Description', 'Series Count']
    self.studiesTableWidget.hideColumn(0)
    self.studiesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.studiesTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    studiesVerticalheader = self.studiesTableWidget.verticalHeader()
    studiesVerticalheader.setDefaultSectionSize(20)
    self.studiesTableWidgetHeader = self.studiesTableWidget.horizontalHeader()

    self.seriesTableHeaderLabels = ['Series Instance UID', 'Status', 'Modality',
                    'Series Date', 'Series Description', 'Body Part Examined',
                    'Series Number','Manufacturer',
                    'Manufacturer Model Name','Instance Count']
    self.seriesTableWidget.hideColumn(0)
    self.seriesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.seriesTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    seriesVerticalheader = self.seriesTableWidget.verticalHeader()
    seriesVerticalheader.setDefaultSectionSize(20)
    self.seriesTableWidgetHeader = self.seriesTableWidget.horizontalHeader()

    # Set icons for buttons
    iconSize = qt.QSize(70, 40)
    self.indexButton.setIcon(downloadAndIndexIcon)
    self.indexButton.setIconSize(iconSize)
    self.loadButton.setIcon(downloadAndLoadIcon)
    self.loadButton.setIconSize(iconSize)
    self.cancelDownloadButton.setIcon(cancelIcon)
    self.cancelDownloadButton.setIconSize(iconSize)

    #
    # delete data context menu
    #
    self.seriesTableWidget.setContextMenuPolicy(2)
    self.removeSeriesAction = qt.QAction("Remove from disk", self.seriesTableWidget)
    self.seriesTableWidget.addAction(self.removeSeriesAction)
    # self.removeSeriesAction.enabled = False

    # Configure storage path and settings
    self.storagePathButton.directory = self.storagePath
    self.storageResetButton.enabled  = True if self.settings.contains("IDCCustomStoragePath") else False

    # Configure web widget checkbox
    self.webWidgetCheckBox.checked = slicer.util.settingsValue("IDCBrowser/ShowWebWidget", False, converter=slicer.util.toBool)
    # only show if developer mode is enabled
    if not self.developerMode:
      self.webWidgetCheckBox.hide()

    # Connect signals
    self.showBrowserButton.connect('clicked(bool)', self.onShowBrowserButton)
    self.unifiedSearchSelector.connect('textChanged(QString)', self.onUnifiedSearchTextChanged)
    self.collectionSelector.connect('currentIndexChanged(QString)', self.collectionSelected)
    self.patientsTableWidget.connect('itemSelectionChanged()', self.patientsTableSelectionChanged)
    self.studiesTableWidget.connect('itemSelectionChanged()', self.studiesTableSelectionChanged)
    self.seriesTableWidget.connect('itemSelectionChanged()', self.seriesSelected)
    self.indexButton.connect('clicked(bool)', self.onIndexButton)
    self.loadButton.connect('clicked(bool)', self.onLoadButton)
    self.cancelDownloadButton.connect('clicked(bool)', self.onCancelDownloadButton)
    self.storagePathButton.connect('directoryChanged(const QString &)', self.onStoragePathButton)
    self.storageResetButton.connect('clicked(bool)', self.onStorageResetButton)
    self.removeSeriesAction.connect('triggered()', self.onRemoveSeriesContextMenuTriggered)
    self.seriesSelectAllButton.connect('clicked(bool)', self.onSeriesSelectAllButton)
    self.seriesSelectNoneButton.connect('clicked(bool)', self.onSeriesSelectNoneButton)
    self.studiesSelectAllButton.connect('clicked(bool)', self.onStudiesSelectAllButton)
    self.studiesSelectNoneButton.connect('clicked(bool)', self.onStudiesSelectNoneButton)
    self.webWidgetCheckBox.connect('toggled(bool)', self.onWebWidgetToggled)

    # Hide the progress bar initially
    self.hideProgressBar()

    # This variable is set to true if we temporarily
    # hide the data probe (and so we need to restore its visibility).
    self.dataProbeHasBeenTemporarilyHidden = False

    # Setup the browser widget layout
    layoutManager = slicer.app.layoutManager()

    self.currentViewArrangement = 0
    self.previousViewArrangement = 0
    self.IDCBrowserLayout = slicer.vtkMRMLLayoutNode.SlicerLayoutUserView + 53
    self.viewFactory = slicer.qSlicerSingletonViewFactory()
    self.viewFactory.setTagName("idcbrowser")
    if layoutManager:
      layoutManager.registerViewFactory(self.viewFactory)
      layoutManager.layoutChanged.connect(self.onLayoutChanged)
      layout = ("""
          <layout type="horizontal">
           <item>
            <idcbrowser></idcbrowser>
           </item>
          </layout>"""
      )
      layoutNode = layoutManager.layoutLogic().GetLayoutNode()
      layoutNode.AddLayoutDescription(self.IDCBrowserLayout, layout)
      self.currentViewArrangement = layoutNode.GetViewArrangement()
      self.previousViewArrangement = layoutNode.GetViewArrangement()

    self.webWidget = slicer.qSlicerWebWidget()
    self.webWidget.setAcceptDrops(False)
    self.webWidget.webView().setAcceptDrops(False)

    updateStyleJS = """
(function injectCSS() {
  const css = `
    .site-header,
    .page-heading,
    .site-footer,
    .download-col,
    .open-viewer,
    .manifest-col
    {
      display: none !important;
      visibility: hidden !important;
    }
    body { margin-top: 0 !important; margin-bottom: 0 !important; }
  `;
  // only add once
  if (!document.getElementById('hide-hf-style'))
  {
    const s = document.createElement('style');
    s.id = 'hide-hf-style';
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  }
})();
"""
    self.webWidget.loadProgress.connect(lambda p: self.webWidget.evalJS(updateStyleJS))
    self.webWidget.url = qt.QUrl("https://portal.imaging.datacommons.cancer.gov/explore/")

    # Create tab widget for browser and web portal
    self.tabWidget = qt.QTabWidget()
    self.tabWidget.setObjectName("IDCBrowserTabWidget")
    self.tabWidget.addTab(self.browserWidget, "Local Browser")
    self.tabWidget.addTab(self.webWidget, "IDC Portal")
    self.viewFactory.setWidget(self.tabWidget)

    # Initialize browser
    if self.showBrowserButton != None and self.showBrowserButton.enabled:
      self.showBrowser()
    if not self.initialConnection:
      self.getCollectionValues()

    self.updateWebWidgetVisibility()
    self.startPythonRequirementsCheck()

  def updateUpgradeRequiredWidget(self):
    """
    Update the GUI elements to reflect the current state of the module.
    """
    if slicer.util.settingsValue("IDCBrowser/PipUpdateRequested", False, converter=slicer.util.toBool):
      self.updateRequiredWidget.show()
    else:
      self.updateRequiredWidget.hide()

  def startPythonRequirementsCheck(self):
    """
    Rather than hanging the GUI to check if any of the libraries need to be updated,
    we will launch a separate process to check for outdated libraries.
    """
    pythonSlicerExecutablePath = os.path.dirname(sys.executable) + "/PythonSlicer"
    if os.name == "nt":
      pythonSlicerExecutablePath += ".exe"

    commandLine = [pythonSlicerExecutablePath, "-m", "pip", "list", "--outdated"]
    self.pipOutdatedLibrariesProc = slicer.util.launchConsoleProcess(commandLine, useStartupEnvironment=False)

    # Check the status/result of the pip list --outdated call every 1 second. Until it is completed.
    self.pythonRequirementsCheckTimer = qt.QTimer()
    self.pythonRequirementsCheckTimer.setInterval(1000)
    self.pythonRequirementsCheckTimer.connect('timeout()', self.onPythonRequirementsCheckTimeout)
    self.pythonRequirementsCheckTimer.setSingleShot(False)
    self.pythonRequirementsCheckTimer.start()

  def onPythonRequirementsCheckTimeout(self):
    """
    Check if the pip outdated libraries process has finished.
    If it has, read the output and check if required libraries are listed as outdated.
    """
    returnCode = self.pipOutdatedLibrariesProc.poll()
    if returnCode is None:
      # Process is still running
      return

    outdatedLibrariesOutput = self.pipOutdatedLibrariesProc.stdout.read()
    self.pythonRequirementsCheckTimer.stop()

    requiredLibraries = [
      "idc-index"
    ]

    outdatedLibraries = []
    for requiredLibrary in requiredLibraries:
      if requiredLibrary in outdatedLibrariesOutput:
        outdatedLibraries.append(requiredLibrary)

    if len(outdatedLibraries) > 0:
      logging.info(f"Required libraries are outdated: {outdatedLibraries}, updating on restart")
      self.settings.setValue("IDCBrowser/PipUpdateRequested", True)

    self.updateUpgradeRequiredWidget()

  def onLayoutChanged(self, viewArrangement):
      self.showBrowserButton.checked = viewArrangement == self.IDCBrowserLayout
      if viewArrangement == self.currentViewArrangement:
          return

      if (self.currentViewArrangement != slicer.vtkMRMLLayoutNode.SlicerLayoutNone
          and self.currentViewArrangement != self.IDCBrowserLayout):
          self.previousViewArrangement = self.currentViewArrangement
      self.currentViewArrangement = viewArrangement

      if self.browserWidget is None:
        return

      mw = slicer.util.mainWindow()
      dataProbe = mw.findChild("QWidget", "DataProbeCollapsibleWidget") if mw else None
      if self.currentViewArrangement == self.IDCBrowserLayout:
          # View has been changed to the IDC browser view
          # If we are in IDC browser module, hide the Data Probe to have more space for the module
          try:
              inIDCBrowserModule = slicer.modules.idcbrowser.widgetRepresentation().isEntered
          except AttributeError:
              # Slicer is shutting down
              inIDCBrowserModule = False
          if inIDCBrowserModule and dataProbe and dataProbe.isVisible():
              dataProbe.setVisible(False)
              self.dataProbeHasBeenTemporarilyHidden = True
      else:
          # View has been changed from the IDC browser view
          if self.dataProbeHasBeenTemporarilyHidden:
              # DataProbe was temporarily hidden, restore its visibility now
              dataProbe.setVisible(True)
              self.dataProbeHasBeenTemporarilyHidden = False

  def cleanup(self):
    pass

  def onShowBrowserButton(self):
    if self.showBrowserButton.checked:
      self.showBrowser()
    else:
      self.closeBrowser()

  # TODO: goes to logic
  def downloadFromQuery(self, query, downloadDestination):
    logging.debug("Downloading from query: " + query)
    manifest_path = os.path.join(downloadDestination,'manifest.csv')
    manifest_df = self.IDCClient.sql_query(query)
    manifest_df.to_csv(manifest_path, index=False, header=False)
    logging.info("Will download to "+downloadDestination)
    self.downloadFromManifestFile(manifest_path, downloadDestination)

  def onUnifiedSearchTextChanged(self, searchText):
    """
    Debounce the search - restarts the timer on each text change.
    """
    self.pendingSearchText = searchText.strip()
    if not self.pendingSearchText:
      self.searchWarningLabel.hide()
      return

    # Reset the timer on each keystroke
    self.searchDebounceTimer.stop()
    self.searchDebounceTimer.start()

  def performUnifiedSearch(self):
    """
    Search for the given text in collection_id, PatientID, StudyInstanceUID, or SeriesInstanceUID.
    Auto-select matching items in the browser.
    """
    if not hasattr(self, 'pendingSearchText'):
      logging.debug("No pending search text")
      return

    # Reset warning
    self.searchWarningLabel.hide()

    searchText = self.pendingSearchText
    if not searchText:
      return

    logging.info(f"Performing unified search for: '{searchText}'")

    # Reset the series-specific search flag (will be set to True only for series searches)
    self.isSearchingForSpecificSeries = False

    # Clear existing selections before starting search
    self.patientsTableWidget.clearSelection()
    self.studiesTableWidget.clearSelection()
    self.seriesTableWidget.clearSelection()

    # Check if IDCClient is initialized
    if not hasattr(self, 'IDCClient') or self.IDCClient is None:
      logging.error("IDCClient not initialized")
      self.searchWarningLabel.setText('Search unavailable - IDC client not initialized.')
      self.searchWarningLabel.show()
      return

    matchFound = False

    try:
      # First, check if it matches a collection_id
      collections = self.IDCClient.get_collections()
      logging.debug(f"Checking against {len(collections)} collections")
      if searchText in collections:
        matchFound = True
        logging.info(f"Found matching collection: {searchText}")
        # Select the collection in the combo box
        index = self.collectionSelector.findText(searchText)
        if index >= 0:
          logging.debug(f"Selecting collection at index {index}")
          self.collectionSelector.setCurrentIndex(index)
          return
        else:
          logging.warning(f"Collection '{searchText}' found in list but not in combo box")

      # Check if it matches a PatientID
      try:
        # Search across all collections for this patient
        logging.debug(f"Searching for PatientID: {searchText}")
        patient_matches = self.IDCClient.index[self.IDCClient.index['PatientID'] == searchText]
        if not patient_matches.empty:
          matchFound = True
          # Get the collection for this patient
          collection_id = patient_matches.iloc[0]['collection_id']
          logging.info(f"Found patient '{searchText}' in collection '{collection_id}'")
          # Select the collection
          index = self.collectionSelector.findText(collection_id)
          if index >= 0:
            self.collectionSelector.setCurrentIndex(index)
            self.selectPatientInTable(searchText)
          else:
            self.searchWarningLabel.setText('Collection for the found series is not available in the selector.')
            self.searchWarningLabel.show()
          return
      except Exception as e:
        logging.debug(f"Error searching for PatientID: {e}")

      # Check if it matches a StudyInstanceUID
      if '.' in searchText:
        try:
          logging.debug(f"Searching for StudyInstanceUID: {searchText}")
          study_matches = self.IDCClient.index[self.IDCClient.index['StudyInstanceUID'] == searchText]
          if not study_matches.empty:
            matchFound = True
            # Get collection and patient for this study
            collection_id = study_matches.iloc[0]['collection_id']
            patient_id = study_matches.iloc[0]['PatientID']
            logging.info(f"Found study '{searchText}' for patient '{patient_id}' in collection '{collection_id}'")
            # Select collection
            index = self.collectionSelector.findText(collection_id)
            if index >= 0:
              self.collectionSelector.setCurrentIndex(index)
              self.selectPatientAndStudy(patient_id, searchText)
            else:
              self.searchWarningLabel.setText('Collection for the found series is not available in the selector.')
              self.searchWarningLabel.show()
            return
        except Exception as e:
          logging.debug(f"Error searching for StudyInstanceUID: {e}")

        # Check if it matches a SeriesInstanceUID
        try:
          logging.debug(f"Searching for SeriesInstanceUID: {searchText}")
          series_matches = self.IDCClient.index[self.IDCClient.index['SeriesInstanceUID'] == searchText]
          if not series_matches.empty:
            matchFound = True
            # Get collection, patient, and study for this series
            collection_id = series_matches.iloc[0]['collection_id']
            patient_id = series_matches.iloc[0]['PatientID']
            study_uid = series_matches.iloc[0]['StudyInstanceUID']
            logging.info(f"Found series '{searchText}' for study '{study_uid}' in collection '{collection_id}'")
            # Set flag to prevent auto-selecting all series
            self.isSearchingForSpecificSeries = True
            # Select collection
            index = self.collectionSelector.findText(collection_id)
            if index >= 0:
              self.collectionSelector.setCurrentIndex(index)
              self.selectPatientStudyAndSeries(patient_id, study_uid, searchText)
            else:
              self.searchWarningLabel.setText('Collection for the found series is not available in the selector.')
              self.searchWarningLabel.show()
            return
        except Exception as e:
          logging.debug(f"Error searching for SeriesInstanceUID: {e}")

      # If no match found, show warning
      if not matchFound:
        self.searchWarningLabel.setText('No matching collection, patient, study, or series found.')
        self.searchWarningLabel.show()

    except Exception as error:
      logging.error(f"Error in unified search: {error}")
      self.searchWarningLabel.setText('Error performing search.')
      self.searchWarningLabel.show()

  def selectPatientInTable(self, patientID):
    """Select a patient in the patients table."""
    for row in range(self.patientsTableWidget.rowCount):
      item = self.patientsTableWidget.item(row, 0)
      if item and item.text() == patientID:
        self.patientsTableWidget.selectRow(row)
        break

  def selectPatientAndStudy(self, patientID, studyUID):
    """Select a patient and then a study in the tables."""
    self.selectPatientInTable(patientID)
    self.selectStudyInTable(studyUID)

  def selectPatientStudyAndSeries(self, patientID, studyUID, seriesUID):
    """Select a patient, study, and series in the tables."""
    self.selectPatientInTable(patientID)
    self.selectStudyAndSeries(studyUID, seriesUID)

  def selectStudyInTable(self, studyUID):
    """Select a study in the studies table."""
    for row in range(self.studiesTableWidget.rowCount):
      item = self.studiesTableWidget.item(row, 0)
      if item and item.text() == studyUID:
        self.studiesTableWidget.selectRow(row)
        break

  def selectStudyAndSeries(self, studyUID, seriesUID):
    """Select a study and then a series in the tables."""
    self.selectStudyInTable(studyUID)
    self.selectSeriesInTable(seriesUID)

  def selectSeriesInTable(self, seriesUID):
    """Select a series in the series table."""
    try:
      for row in range(self.seriesTableWidget.rowCount):
        item = self.seriesTableWidget.item(row, 0)
        if item and item.text() == seriesUID:
          self.seriesTableWidget.selectRow(row)
          break
      # Reset the series-specific search flag after series selection completes
    finally:
      self.isSearchingForSpecificSeries = False

  def onUseCacheStateChanged(self, state):
    if state == 0:
      self.useCacheFlag = False
    elif state == 2:
      self.useCacheFlag = True

  def onContextMenuTriggered(self):
    self.clinicalPopup.getData(self.selectedCollection, self.selectedPatient)

  def onRemoveSeriesContextMenuTriggered(self):
    removeList = []
    for uid in self.seriesInstanceUIDs:
      if uid.isSelected():
        removeList.append(uid.text())
    with open(self.downloadedSeriesArchiveFile, 'rb') as f:
      self.previouslyDownloadedSeries = pickle.load(f)
    f.close()
    updatedDownloadSeries = []
    for item in self.previouslyDownloadedSeries:
      if item not in removeList:
        updatedDownloadSeries.append(item)
    with open(self.downloadedSeriesArchiveFile, 'wb') as f:
      pickle.dump(updatedDownloadSeries,f)
    f.close()
    self.previouslyDownloadedSeries = updatedDownloadSeries
    self.studiesTableSelectionChanged()

  def showBrowser(self):
    slicer.app.layoutManager().setLayout(self.IDCBrowserLayout)

  def closeBrowser(self):
    if (self.currentViewArrangement != self.IDCBrowserLayout
        and self.currentViewArrangement != slicer.vtkMRMLLayoutNode.SlicerLayoutNone):
      # current layout is a valid layout that is not the IDC browser view, so nothing to do
      return

    # Use a default layout if this layout is not valid
    layoutId = self.previousViewArrangement
    if (layoutId == slicer.vtkMRMLLayoutNode.SlicerLayoutNone
        or layoutId == self.IDCBrowserLayout):
      layoutId = qt.QSettings().value("MainWindow/layout", slicer.vtkMRMLLayoutNode.SlicerLayoutInitialView)

    slicer.app.layoutManager().setLayout(layoutId)

  def showStatus(self, message, waitMessage='Waiting for IDC server .... '):
    self.statusLabel.text = waitMessage + message
    self.statusLabel.setStyleSheet("QLabel { background-color : #F0F0F0 ; color : #383838; }")
    slicer.app.processEvents()

  def clearStatus(self):
    self.statusLabel.text = ''
    self.statusLabel.setStyleSheet("QLabel { background-color : white; color : black; }")

  def onStoragePathButton(self):
    self.storagePath = self.storagePathButton.directory
    self.settings.setValue("IDCCustomStoragePath", self.storagePath)
    self.storageResetButton.enabled = True

  def onStorageResetButton(self):
    self.storagePath = self.settings.value("IDCDefaultStoragePath")
    self.settings.remove("IDCCustomStoragePath")
    self.storageResetButton.enabled = False
    self.storagePathButton.directory = self.storagePath

  def getCollectionValues(self):
    self.initialConnection = True

    self.showStatus("Getting Available Collections")
    try:
      responseString = self.IDCClient.get_collections()
      logging.debug("getCollectionValues: responseString = " + str(responseString))
      self.populateCollectionsTreeView(responseString)
      self.clearStatus()

    except Exception as error:
      self.connectButton.enabled = True
      self.clearStatus()
      message = "getCollectionValues: Error in getting response from IDC server.\nHTTP Error:\n" + str(error)
      qt.QMessageBox.critical(slicer.util.mainWindow(),
                  'SlicerIDCBrowser', message, qt.QMessageBox.Ok)
    self.showBrowserButton.enabled = True
    self.showBrowser()

  def enter(self):
    qt.QTimer.singleShot(0, self.showBrowser)

  def exit(self):
    self.closeBrowser()

  def onStudiesSelectAllButton(self):
    self.studiesTableWidget.selectAll()

  def onStudiesSelectNoneButton(self):
    self.studiesTableWidget.clearSelection()

  def onSeriesSelectAllButton(self):
    self.seriesTableWidget.selectAll()

  def onSeriesSelectNoneButton(self):
    self.seriesTableWidget.clearSelection()

  def onWebWidgetToggled(self, checked):
    self.settings.setValue("IDCBrowser/ShowWebWidget", checked)
    self.updateWebWidgetVisibility()

  def updateWebWidgetVisibility(self):
    if self.tabWidget is None:
      return
    showWebWidget = slicer.util.settingsValue("IDCBrowser/ShowWebWidget", False, converter=slicer.util.toBool)
    self.tabWidget.tabBar().setVisible(showWebWidget)

  def collectionSelected(self, item):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    self.clearPatientsTableWidget()
    self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.selectedCollection = item
    cacheFile = self.cachePath + self.selectedCollection + '.json'
    self.progressMessage = "Getting available patients for collection: " + self.selectedCollection

    # make collection summary
    collection_summary = self.IDCClient.collection_summary.loc[self.selectedCollection]
    if float(collection_summary.series_size_MB) > 1000:
      summary_text = "Modalities: "+str(collection_summary.Modality).replace('\'','')+" Total size: "+str(round(float(collection_summary.series_size_MB)/1000,2))+" GB"
    else:
      summary_text = "Modalities: "+str(collection_summary.Modality).replace('\'','')+" Total size: "+str(round(float(collection_summary.series_size_MB),2))+" MB"
    self.logoLabel.setText(summary_text)

    patientsList = None
    if os.path.isfile(cacheFile) and self.useCacheFlag:
      f = codecs.open(cacheFile, 'rb', encoding='utf8')
      patientsList = f.read()[:]
      f.close()

      if not len(patientsList):
        patientsList = None

    if patientsList:
      self.populatePatientsTableWidget(patientsList)
      self.clearStatus()
      #groupBoxTitle = 'Patients (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
      groupBoxTitle = 'Patients'
      self.patientsCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      try:
        responseString = self.IDCClient.get_patients(collection_id=self.selectedCollection)
        '''
        with open(cacheFile, 'w') as outputFile:
          self.stringBufferReadWrite(outputFile, response)
        outputFile.close()
        f = codecs.open(cacheFile, 'r', encoding='utf8')
        responseString = f.read()
        '''
        self.populatePatientsTableWidget(responseString)
        #groupBoxTitle = 'Patients (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
        groupBoxTitle = 'Patients'
        self.patientsCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception as error:
        self.clearStatus()
        message = "collectionSelected: Error in getting response from IDC server.\nHTTP Error:\n" + str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                    'SlicerIDCBrowser', message, qt.QMessageBox.Ok)

  def patientsTableSelectionChanged(self):
    self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.studiesTableRowCount = 0
    self.numberOfSelectedPatients = 0
    for n in range(len(self.patientsIDs)):
      if self.patientsIDs[n].isSelected():
        self.numberOfSelectedPatients += 1
        self.patientSelected(n)

  def patientSelected(self, row):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    # self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.selectedPatient = self.patientsIDs[row].text()
    cacheFile = self.cachePath + self.selectedPatient + '.json'
    self.progressMessage = "Getting available studies for patient ID: " + self.selectedPatient
    self.showStatus(self.progressMessage)
    if os.path.isfile(cacheFile) and self.useCacheFlag:
      f = codecs.open(cacheFile, 'rb', encoding='utf8')
      responseString = f.read()[:]
      f.close()
      self.populateStudiesTableWidget(responseString)
      self.clearStatus()
      if self.numberOfSelectedPatients == 1:
        #groupBoxTitle = 'Studies (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
        groupBoxTitle = 'Studies '
      else:
        groupBoxTitle = 'Studies '

      self.studiesCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      try:
        responseString = self.IDCClient.get_dicom_studies(patientId=self.selectedPatient)
        '''
        with open(cacheFile, 'wb') as outputFile:
          outputFile.write(responseString)
          outputFile.close()
        f = codecs.open(cacheFile, 'rb', encoding='utf8')
        responseString = f.read()[:]
        '''
        self.populateStudiesTableWidget(responseString)
        if self.numberOfSelectedPatients == 1:
          #groupBoxTitle = 'Studies (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
          groupBoxTitle = 'Studies '
        else:
          groupBoxTitle = 'Studies '

        self.studiesCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception as error:
        self.clearStatus()
        message = "patientSelected: Error in getting response from IDC server.\nHTTP Error:\n" + str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                    'SlicerIDCBrowser', message, qt.QMessageBox.Ok)

  def studiesTableSelectionChanged(self):
    self.clearSeriesTableWidget()
    self.seriesTableRowCount = 0
    self.numberOfSelectedStudies = 0
    for n in range(len(self.studyInstanceUIDs)):
      if self.studyInstanceUIDs[n].isSelected():
        self.numberOfSelectedStudies += 1
        self.studySelected(n)

  def studySelected(self, row):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    self.selectedStudy = self.studyInstanceUIDs[row].text()
    self.selectedStudyRow = row
    self.progressMessage = "Getting available series for studyInstanceUID: " + self.selectedStudy
    self.showStatus(self.progressMessage)
    cacheFile = self.cachePath + self.selectedStudy + '.json'
    if os.path.isfile(cacheFile) and self.useCacheFlag:
      logging.debug("studySelected: using cache file: " + cacheFile)
      f = codecs.open(cacheFile, 'rb', encoding='utf8')
      responseString = f.read()[:]
      f.close()
      self.populateSeriesTableWidget(responseString)
      self.clearStatus()
      if self.numberOfSelectedStudies == 1:
        #groupBoxTitle = 'Series (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
        groupBoxTitle = 'Series '
      else:
        groupBoxTitle = 'Series '

      self.seriesCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      self.progressMessage = "Getting available series for studyInstanceUID: " + self.selectedStudy
      self.showStatus(self.progressMessage)
      try:
        responseString = self.IDCClient.get_dicom_series(studyInstanceUID=self.selectedStudy)
        '''
        with open(cacheFile, 'wb') as outputFile:
          outputFile.write(responseString)
          outputFile.close()
        '''

        self.populateSeriesTableWidget(responseString)

        if self.numberOfSelectedStudies == 1:
          #groupBoxTitle = 'Series (Accessed: ' + time.ctime(os.path.getmtime(cacheFile)) + ')'
          groupBoxTitle = 'Series '
        else:
          groupBoxTitle = 'Series '

        self.seriesCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception as error:
        self.clearStatus()
        message = "studySelected: Error in getting response from IDC server.\nHTTP Error:\n" + str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                    'SlicerIDCBrowser', message, qt.QMessageBox.Ok)

    # Only auto-select all series if we're not searching for a specific series
    if not getattr(self, 'isSearchingForSpecificSeries', False):
      self.onSeriesSelectAllButton()
    # self.loadButton.enabled = True
    # self.indexButton.enabled = True

  def seriesSelected(self):
    self.imagesToDownloadCount = 0
    self.imagesToDownloadSize = 0
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    for n in range(len(self.seriesInstanceUIDs)):
      if self.seriesInstanceUIDs[n].isSelected():
        self.imagesToDownloadCount += int(self.imageCounts[n].text())
        self.imagesToDownloadSize += float(self.imageSizes[n])
        self.loadButton.enabled = True
        self.indexButton.enabled = True
    if self.imagesToDownloadSize > 1000:
      self.imagesToDownloadSize = self.imagesToDownloadSize / 1000
      unit = 'GB'
    else:
      unit = 'MB'
    self.imagesCountLabel.text = 'Total size to download: ' + '<span style=" font-weight:600; color:#aa0000;">' + str(
      round(self.imagesToDownloadSize,2)) + unit+'</span>' + ' '

  def onIndexButton(self):
    self.loadToScene = False
    self.addSelectedToDownloadQueue()
    # self.addFilesToDatabase()

  def onLoadButton(self):
    self.loadToScene = True
    startTime = time.time()
    self.addSelectedToDownloadQueue()
    logging.info('onLoadButton: Done in {0:.2f} seconds.'.format(time.time() - startTime))

  def onCancelDownloadButton(self):
    self.cancelDownload = True
    self.downloadQueue = {}
    self.seriesRowNumber = {}
    self.hideProgressBar()

  def hideProgressBar(self):
    self.downloadProgressBar.hide()
    self.downloadProgressBar.setValue(0)

  def showProgressBar(self):
    self.downloadProgressBar.show()

  def addFilesToDatabase(self, directory=None):
    self.progressMessage = "Adding Files to DICOM Database "
    self.showStatus(self.progressMessage)

    indexer = ctk.ctkDICOMIndexer()
    # DICOM indexer uses the current DICOM database folder as the basis for relative paths,
    # therefore we must convert the folder path to absolute to ensure this code works
    # even when a relative path is used as self.extractedFilesDirectories.
    if not directory:
      for extractedFilesDirectory in self.extractedFilesDirectories:
        indexer.addDirectory(slicer.app.dicomDatabase(), os.path.abspath(extractedFilesDirectory))
    else:
      indexer.addDirectory(slicer.app.dicomDatabase(), os.path.abspath(directory))
    indexer.waitForImportFinished()
    self.clearStatus()

  def addSelectedToDownloadQueue(self):
    self.cancelDownload = False
    allSelectedSeriesUIDs = []
    self.downloadQueue = {}
    self.seriesRowNumber = {}

    for n in range(len(self.seriesInstanceUIDs)):
      if self.seriesInstanceUIDs[n].isSelected():
        selectedCollection = self.selectedCollection
        selectedPatient = self.selectedPatient
        selectedStudy = self.selectedStudy
        selectedSeries = self.seriesInstanceUIDs[n].text()
        allSelectedSeriesUIDs.append(selectedSeries)
        # selectedSeries = self.selectedSeriesUIdForDownload
        self.selectedSeriesNicknamesDic[selectedSeries] = str(selectedPatient
                                    ) + '-' + str(
          self.selectedStudyRow + 1) + '-' + str(n + 1)

        # create download queue
        self.showProgressBar()
        self.downloadQueue[selectedSeries] = self.storagePath
        self.seriesRowNumber[selectedSeries] = n

    self.seriesTableWidget.clearSelection()
    self.patientsTableWidget.enabled = False
    self.studiesTableWidget.enabled = False
    self.collectionSelector.enabled = False
    self.downloadSelectedSeries()

    if self.loadToScene:
      failedSeriesCount = 0
      for seriesUID in allSelectedSeriesUIDs:
        logging.debug("Loading series: " + seriesUID)
        #if any(seriesUID == s for s in self.previouslyDownloadedSeries):
        if True:
          self.progressMessage = "Examine Files to Load"
          self.showStatus(self.progressMessage, '')
          plugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
          seriesUID = seriesUID.replace("'", "")
          dicomDatabase = slicer.app.dicomDatabase()
          fileList = slicer.app.dicomDatabase().filesForSeries(seriesUID)
          loadables = []

          try:
            loadables = plugin.examine([fileList])
          except Exception as error:
            failedSeriesCount += 1

          self.clearStatus()
          if len(loadables)>0:
            volume = plugin.load(loadables[0])
            if volume:
              logging.debug("Loaded volume: " + volume.GetName())
            else:
              failedSeriesCount += 1
          else:
            failedSeriesCount += 1

      if failedSeriesCount > 0:
        message = "Download was successful, but failed to load " + str(failedSeriesCount) + \
          " series into the Slicer scene. You can retry loading from DICOM Browser!"
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                    'SlicerIDCBrowser', message, qt.QMessageBox.Ok)

  def downloadSelectedSeries(self):

    if len(self.downloadQueue) == 0:
      logging.debug("No series selected for download")
      return

    self.extractedFilesDirectories = set()

    downloadQueueData = { 'SeriesInstanceUID': self.downloadQueue.keys(),
             'DownloadFolder': self.downloadQueue.values() }

    import pandas as pd
    manifest_df = pd.DataFrame.from_dict(downloadQueueData)
    manifest_df = manifest_df.merge(self.IDCClient.index, on='SeriesInstanceUID', how='left')
    manifestContents = "\n".join(
      f"cp {url} {folder}"
      for url, folder in zip(manifest_df["series_aws_url"], manifest_df["DownloadFolder"])
      )

    self.cancelDownloadButton.enabled = True

    self.extractedFilesDirectories.update(manifest_df["DownloadFolder"].tolist())
    for downloadFolderPath in self.extractedFilesDirectories:
      if not os.path.exists(downloadFolderPath):
        logging.debug("Creating directory to keep the downloads: " + downloadFolderPath)
        os.makedirs(downloadFolderPath)

    self.progressMessage = "Downloading Images for selected series"
    self.showStatus(self.progressMessage)
    logging.debug(self.progressMessage)

    try:
      start_time = time.time()

      # write manifest to a temporary file
      manifest_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
      manifest_file.write(manifestContents)
      manifest_file.close()
      logging.debug("Manifest file created: " + manifest_file.name)

      self.downloadFromManifestFile(manifest_file.name, self.storagePath)

      os.remove(manifest_file.name)
      slicer.app.processEvents()
      logging.debug("Downloaded images in %s seconds" % (time.time() - start_time))

      try:
        start_time = time.time()
        for directory in self.extractedFilesDirectories:
          self.addFilesToDatabase(directory)
        logging.debug("Added files to database in %s seconds" % (time.time() - start_time))

        for selectedSeries in self.downloadQueue.keys():
          self.previouslyDownloadedSeries.append(selectedSeries)
          n = self.seriesRowNumber[selectedSeries]
          table = self.seriesTableWidget
          item = table.item(n, 1)
          item.setIcon(self.storedlIcon)

      except Exception as error:
        import traceback
        traceback.print_exc()
        logging.error("Failed to add images to the database!")

    except Exception as error:
      import traceback
      traceback.print_exc()
      self.clearStatus()
      message = "downloadSelectedSeries: Failed to download " + str(error)
      qt.QMessageBox.critical(slicer.util.mainWindow(),
                  'SlicerIDCBrowser', message, qt.QMessageBox.Ok)

    finally:
      self.hideProgressBar()

    self.downloadQueue = {}
    self.cancelDownloadButton.enabled = False
    self.collectionSelector.enabled = True
    self.patientsTableWidget.enabled = True
    self.studiesTableWidget.enabled = True

  def stringBufferReadWrite(self, dstFile, responseString, bufferSize=819):
      dstFile.write(responseString)

  def updateProgressBar(self, currentValue, totalValue, unit="B", description=""):
    units = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB"]
    for currentUnit in units:
        unit = currentUnit
        if abs(totalValue) < 1000.0 or currentUnit == units[-1]:
            break
        totalValue /= 1000.0
        currentValue /= 1000.0
    self.downloadProgressBar.setMaximum(int(totalValue))
    self.downloadProgressBar.setValue(int(currentValue))
    self.downloadProgressBar.setFormat(f"{description + ' ' if description else ''}%p% (%v{unit}/%m{unit})")
    slicer.app.processEvents()

  def unzip(self, sourceFilename, destinationDir):
    totalItems = 0
    with zipfile.ZipFile(sourceFilename) as zf:
      for member in zf.infolist():
        logging.debug("Found item %s in archive" % member.filename)
        words = member.filename.split('/')
        path = destinationDir
        for word in words[:-1]:
          drive, word = os.path.splitdrive(word)
          head, word = os.path.split(word)
          if word in (os.curdir, os.pardir, ''): continue
          path = os.path.join(path, word)
        logging.debug("Extracting %s" % words[-1])
        zf.extract(member, path)
        try:
          dcm = pydicom.read_file(os.path.join(path,words[-1]))
          totalItems = totalItems + 1
        except:
          pass
    logging.debug("Total %i DICOM items extracted from image archive." % totalItems)
    return totalItems

  def getSeriesSize(self, seriesInstanceUID):
    size = self.IDCClient.get_series_size(seriesInstanceUID)
    return size

  def populateCollectionsTreeView(self, responseString):
      collectionNames = sorted(responseString)

      savedCollection = self.collectionSelector.currentText

      wasBlocked = self.collectionSelector.blockSignals(True)
      self.collectionSelector.clear()
      self.collectionSelector.addItems(collectionNames)
      self.collectionSelector.blockSignals(wasBlocked)

      if savedCollection in collectionNames:
        index = self.collectionSelector.findText(savedCollection)
        self.collectionSelector.setCurrentIndex(index)
      else:
        # Select the first collection
        self.collectionSelector.setCurrentIndex(-1) # temporarily set to -1 to force change
        self.collectionSelector.setCurrentIndex(0)

      # Set up the completer with the same items
      self.collectionCompleter.setModel(self.collectionSelector.model())


  def populatePatientsTableWidget(self, responseString):
    logging.debug("populatePatientsTableWidget")
    self.clearPatientsTableWidget()
    table = self.patientsTableWidget
    patients = responseString
    table.setRowCount(len(patients))
    n = 0
    for patient in patients:
      keys = patient.keys()
      for key in keys:
        if key == 'PatientID':
          logging.debug("PatientID: %s" % patient['PatientID'])
          patientIDString = str(patient['PatientID'])
          patientID = qt.QTableWidgetItem(patientIDString)
          self.patientsIDs.append(patientID)
          table.setItem(n, 0, patientID)
          if patientIDString[0:4] == 'TCGA':
            patientID.setIcon(self.reportIcon)
        if key == 'PatientSex':
          patientSex = qt.QTableWidgetItem(str(patient['PatientSex']))
          self.patientSexes.append(patientSex)
          table.setItem(n, 1, patientSex)
        if key == 'PatientAge':
          patientAge = qt.QTableWidgetItem(str(patient['PatientAge']))
          self.patientAges.append(patientAge)
          table.setItem(n, 2, patientAge)
      n += 1
    self.patientsTableWidget.resizeColumnsToContents()
    self.patientsTableWidgetHeader.setStretchLastSection(True)

  def populateStudiesTableWidget(self, responseString):
    self.studiesSelectAllButton.enabled = True
    self.studiesSelectNoneButton.enabled = True
    # self.clearStudiesTableWidget()
    table = self.studiesTableWidget
    studies = responseString

    n = self.studiesTableRowCount
    table.setRowCount(n + len(studies))

    for study in studies:
      keys = study.keys()
      for key in keys:
        if key == 'StudyInstanceUID':
          studyInstanceUID = qt.QTableWidgetItem(str(study['StudyInstanceUID']))
          self.studyInstanceUIDs.append(studyInstanceUID)
          table.setItem(n, 0, studyInstanceUID)
        if key == 'StudyDate':
          studyDate = qt.QTableWidgetItem(str(study['StudyDate']))
          self.studyDates.append(studyDate)
          table.setItem(n, 1, studyDate)
        if key == 'StudyDescription':
          studyDescription = qt.QTableWidgetItem(str(study['StudyDescription']))
          self.studyDescriptions.append(studyDescription)
          table.setItem(n, 2, studyDescription)
        if key == 'SeriesCount':
          seriesCount = qt.QTableWidgetItem(str(study['SeriesCount']))
          self.seriesCounts.append(seriesCount)
          table.setItem(n, 3, seriesCount)
      n += 1
    self.studiesTableWidget.resizeColumnsToContents()
    self.studiesTableWidgetHeader.setStretchLastSection(True)
    self.studiesTableRowCount = n

  def populateSeriesTableWidget(self, responseString):
    logging.debug("populateSeriesTableWidget")
    # self.clearSeriesTableWidget()
    table = self.seriesTableWidget
    seriesCollection = responseString
    self.seriesSelectAllButton.enabled = True
    self.seriesSelectNoneButton.enabled = True

    n = self.seriesTableRowCount
    table.setRowCount(n + len(seriesCollection))

    for series in seriesCollection:
      keys = series.keys()
      for key in keys:
        if key == 'SeriesInstanceUID':
          seriesInstanceUID = str(series['SeriesInstanceUID'])
          seriesInstanceUIDItem = qt.QTableWidgetItem(seriesInstanceUID)
          self.seriesInstanceUIDs.append(seriesInstanceUIDItem)
          table.setItem(n, 0, seriesInstanceUIDItem)
          if any(seriesInstanceUID == s for s in self.previouslyDownloadedSeries):
            self.removeSeriesAction.enabled = True
            icon = self.storedlIcon
          else:
            icon = self.downloadIcon
          downloadStatusItem = qt.QTableWidgetItem(str(''))
          downloadStatusItem.setTextAlignment(qt.Qt.AlignCenter)
          downloadStatusItem.setIcon(icon)
          self.downloadStatusCollection.append(downloadStatusItem)
          table.setItem(n, 1, downloadStatusItem)
        if key == 'Modality':
          modality = qt.QTableWidgetItem(str(series['Modality']))
          self.modalities.append(modality)
          table.setItem(n, 2, modality)
        if key == 'SeriesDate':
          seriesDate = qt.QTableWidgetItem(str(series['SeriesDate']))
          self.seriesDates.append(seriesDate)
          table.setItem(n, 3, seriesDate)
        if key == 'SeriesDescription':
          seriesDescription = qt.QTableWidgetItem(str(series['SeriesDescription']))
          self.seriesDescriptions.append(seriesDescription)
          table.setItem(n, 4, seriesDescription)
        if key == 'BodyPartExamined':
          bodyPartExamined = qt.QTableWidgetItem(str(series['BodyPartExamined']))
          self.bodyPartsExamined.append(bodyPartExamined)
          table.setItem(n, 5, bodyPartExamined)
        if key == 'SeriesNumber':
          seriesNumber = qt.QTableWidgetItem(str(series['SeriesNumber']))
          self.seriesNumbers.append(seriesNumber)
          table.setItem(n, 6, seriesNumber)
        if key == 'Manufacturer':
          manufacturer = qt.QTableWidgetItem(str(series['Manufacturer']))
          self.manufacturers.append(manufacturer)
          table.setItem(n, 7, manufacturer)
        if key == 'ManufacturerModelName':
          manufacturerModelName = qt.QTableWidgetItem(str(series['ManufacturerModelName']))
          self.manufacturerModelNames.append(manufacturerModelName)
          table.setItem(n, 8, manufacturerModelName)
        if key == 'ImageCount':
          imageCount = qt.QTableWidgetItem(str(series['ImageCount']))
          self.imageCounts.append(imageCount)
          self.imageSizes.append(float(series['series_size_MB']))
          table.setItem(n, 9, imageCount)
      n += 1
    self.seriesTableWidget.resizeColumnsToContents()
    self.seriesTableRowCount = n
    self.seriesTableWidgetHeader.setStretchLastSection(True)

  def clearPatientsTableWidget(self):
    table = self.patientsTableWidget
    self.patientsCollapsibleGroupBox.setTitle('Patients')
    self.patientsIDs = []
    self.patientNames = []
    self.patientBirthDates = []
    self.patientSexes = []
    self.patientAges = []
    self.ethnicGroups = []
    # self.collections = []
    table.clear()
    table.setHorizontalHeaderLabels(self.patientsTableHeaderLabels)

  def clearStudiesTableWidget(self):
    self.studiesTableRowCount = 0
    table = self.studiesTableWidget
    self.studiesCollapsibleGroupBox.setTitle('Studies')
    self.studyInstanceUIDs = []
    self.studyDates = []
    self.studyDescriptions = []
    self.admittingDiagnosesDescriptions = []
    self.studyIDs = []
    self.patientAges = []
    self.seriesCounts = []
    table.clear()
    table.setHorizontalHeaderLabels(self.studiesTableHeaderLabels)

  def clearSeriesTableWidget(self):
    self.seriesTableRowCount = 0
    table = self.seriesTableWidget
    self.seriesCollapsibleGroupBox.setTitle('Series')
    self.seriesInstanceUIDs = []
    self.downloadStatusCollection = []
    self.modalities = []
    self.protocolNames = []
    self.seriesDates = []
    self.seriesDescriptions = []
    self.bodyPartsExamined = []
    self.seriesNumbers = []
    self.annotationsFlags = []
    self.manufacturers = []
    self.manufacturerModelNames = []
    self.softwareVersionsCollection = []
    self.imageCounts = []
    self.imageSizes = []
    table.clear()
    table.setHorizontalHeaderLabels(self.seriesTableHeaderLabels)

  def downloadFromManifestFile(self, filePath, downloadDir=None):
    if downloadDir is None:
        downloadDir = self.downloadDestinationSelector.directory

    try:
      self.showProgressBar()
      slicer.app.processEvents()
      if 'progress_callback' in inspect.signature(self.IDCClient.download_from_manifest).parameters:
        self.IDCClient.download_from_manifest(manifestFile=filePath, downloadDir=downloadDir, progress_callback=self.updateProgressBar)
      else:
        self.IDCClient.download_from_manifest(manifestFile=filePath, downloadDir=downloadDir)
    except Exception as error:
      self.download_status.setText('Download from manifest failed.')
      logging.error('Download from manifest failed.')
      logging.error(error)
      return
    finally:
      self.hideProgressBar()
      slicer.app.processEvents()

    return True

#
# IDCBrowserLogic
#

class IDCBrowserLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget
  """

  def __init__(self):
    self.idc_index_location = None
    self.idc_version = None
    pass

  def setupPythonRequirements(self, update=False):
    needToInstall = False
    try:
        import idc_index
    except ModuleNotFoundError as e:
      needToInstall=True

    installed = False
    if needToInstall or update:
      userMessage = "The current idc-index python package is out of date, and will now be updated."
      errorMessage = f"Failed to {'install' if needToInstall else 'update'} idc-index."
      if needToInstall:
        userMessage = "The module requires idc-index python package, which will now be installed."
      logging.info(userMessage)
      with slicer.util.displayPythonShell() as shell, slicer.util.tryWithErrorDisplay(message=errorMessage, waitCursor=True) as errorDisplay:
        slicer.util.pip_install(f"{'--upgrade ' if update else ''}idc-index>=0.7.0")
        installed = True
    else:
      installed = True

    if installed or not needToInstall:
      from idc_index import index
      self.idc_index_location = index.__file__
      self.idc_version = index.IDCClient.get_idc_version()
    return installed

  def hasImageData(self, volumeNode):
    """This is a dummy logic method that
    returns true if the passed in volume
    node has valid image data
    """
    if not volumeNode:
      print('no volume node')
      return False
    if volumeNode.GetImageData() == None:
      print('no image data')
      return False
    return True

  def delayDisplay(self, message, msec=1000):
    #
    # logic version of delay display
    #
    print(message)
    self.info = qt.QDialog()
    self.infoLayout = qt.QVBoxLayout()
    self.info.setLayout(self.infoLayout)
    self.label = qt.QLabel(message, self.info)
    self.infoLayout.addWidget(self.label)
    qt.QTimer.singleShot(msec, self.info.close)
    self.info.exec_()

  def takeScreenshot(self, name, description, type=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if type == -1:
      # full window
      widget = slicer.util.mainWindow()
    elif type == slicer.qMRMLScreenShotDialog().FullLayout:
      # full layout
      widget = lm.viewport()
    elif type == slicer.qMRMLScreenShotDialog().ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif type == slicer.qMRMLScreenShotDialog().Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif type == slicer.qMRMLScreenShotDialog().Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif type == slicer.qMRMLScreenShotDialog().Green:
      # green slice window
      widget = lm.sliceWidget("Green")

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage, imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, type, self.screenshotScaleFactor, imageData)

  def run(self, inputVolume, outputVolume, enableScreenshots=0, screenshotScaleFactor=1):
    """
    Run the actual algorithm
    """

    self.delayDisplay('Running the aglorithm')

    self.enableScreenshots = enableScreenshots
    self.screenshotScaleFactor = screenshotScaleFactor

    self.takeScreenshot('IDCBrowser-Start', 'Start', -1)

    return True

  def getIDCIndexPath(self):
    idc_index_pip_dir = os.path.dirname(self.idc_index_location)
    return os.path.join(idc_index_pip_dir,'idc_index.csv.zip')

class IDCBrowserFileReader:
  def __init__(self, parent):
    self.parent = parent

  def description(self):
    return "s5cmd manifest file"

  def fileType(self):
    return "s5cmdManifest"

  def extensions(self):
    return ["s5cmd manifest file (*.s5cmd)"]

  def canLoadFile(self, filePath):
    return True

  def load(self, properties):
    if properties['fileType'] != self.fileType():
      return False

    fileName = properties['fileName']
    if not os.path.isfile(fileName):
      logging.error('IDCBrowserFileReader: file does not exist: ' + fileName)
      return False

    slicer.util.selectModule("IDCBrowser")
    slicer.app.processEvents()
    idcBrowserWidget = slicer.modules.idcbrowser.widgetRepresentation().self()
    success = idcBrowserWidget.downloadFromManifestFile(fileName, idcBrowserWidget.storagePath)
    slicer.app.processEvents()
    idcBrowserWidget.addFilesToDatabase(idcBrowserWidget.storagePath)
    return success

class IDCBrowserTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  """

  def delayDisplay(self, message, msec=1000):
    """This utility method displays a small dialog and waits.
    This does two things: 1) it lets the event loop catch up
    to the state of the test so that rendering and widget updates
    have all taken place before the test continues and 2) it
    shows the user/developer/tester the state of the test
    so that we'll know when it breaks.
    """
    print(message)
    self.info = qt.QDialog()
    self.infoLayout = qt.QVBoxLayout()
    self.info.setLayout(self.infoLayout)
    self.label = qt.QLabel(message, self.info)
    self.infoLayout.addWidget(self.label)
    qt.QTimer.singleShot(msec, self.info.close)
    self.info.exec_()

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    import traceback
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.testBrowserDownloadAndLoad()

  def testBrowserDownloadAndLoad(self):
    self.delayDisplay("Starting the test")
    widget = IDCBrowserWidget(None)
    widget.getCollectionValues()
    browserWindow = widget.browserWidget
    collectionsCombobox = browserWindow.findChildren('QComboBox')[0]
    print('Number of collections: {}'.format(collectionsCombobox.count))
    if collectionsCombobox.count > 0:
      collectionsCombobox.setCurrentIndex(randint(0, collectionsCombobox.count - 1))
      currentCollection = collectionsCombobox.currentText
      if currentCollection != '':
        print('connected to the server successfully')
        print('current collection: {}'.format(currentCollection))

      tableWidgets = browserWindow.findChildren('QTableWidget')

      patientsTable = tableWidgets[0]
      if patientsTable.rowCount > 0:
        selectedRow = randint(0, patientsTable.rowCount - 1)
        selectedPatient = patientsTable.item(selectedRow, 0).text()
        if selectedPatient != '':
          print('selected patient: {}'.format(selectedPatient))
          patientsTable.selectRow(selectedRow)

        studiesTable = tableWidgets[1]
        if studiesTable.rowCount > 0:
          selectedRow = randint(0, studiesTable.rowCount - 1)
          selectedStudy = studiesTable.item(selectedRow, 0).text()
          if selectedStudy != '':
            print('selected study: {}'.format(selectedStudy))
            studiesTable.selectRow(selectedRow)

          seriesTable = tableWidgets[2]
          if seriesTable.rowCount > 0:
            selectedRow = randint(0, seriesTable.rowCount - 1)
            selectedSeries = seriesTable.item(selectedRow, 0).text()
            if selectedSeries != '':
              print('selected series to download: {}'.format(selectedSeries))
              seriesTable.selectRow(selectedRow)

            pushButtons = browserWindow.findChildren('QPushButton')
            for pushButton in pushButtons:
              toolTip = pushButton.toolTip
              if toolTip[16:20] == 'Load':
                loadButton = pushButton

            if loadButton != None:
              loadButton.click()
            else:
              print('could not find Load button')
    else:
      print("Test Failed. No collection found.")
    scene = slicer.mrmlScene
    self.assertEqual(scene.GetNumberOfNodesByClass('vtkMRMLScalarVolumeNode'), 1)
    self.delayDisplay('Browser Test Passed!')
