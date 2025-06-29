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

    self.browserWidget = qt.QWidget()
    self.browserWidget.setWindowTitle('SlicerIDCBrowser | NCI Imaging Data Commons data release '+self.logic.idc_version)

    self.initialConnection = False
    self.seriesTableRowCount = 0
    self.studiesTableRowCount = 0
    self.downloadProgressBars = {}
    self.downloadProgressLabels = {}
    self.selectedSeriesNicknamesDic = {}
    self.downloadQueue = {}
    self.seriesRowNumber = {}

    self.imagesToDownloadCount = 0

    self.downloadProgressBarWidgets = []

    item = qt.QStandardItem()

    # Put the files downloaded from IDC in the DICOM database folder by default.
    # This makes downloaded files relocatable along with the DICOM database in
    # recent Slicer versions.

    if not os.path.isfile(slicer.dicomDatabase.databaseFilename):
      dicomBrowser = ctk.ctkDICOMBrowser()
      dicomBrowser.databaseDirectory = slicer.dicomDatabase.databaseDirectory
      dicomBrowser.createNewDatabaseDirectory()
      slicer.dicomDatabase.openDatabase(slicer.dicomDatabase.databaseFilename)
      logging.info("DICOM database created")
    else:
      logging.info('DICOM database is available at '+slicer.dicomDatabase.databaseFilename)
      slicer.dicomDatabase.updateSchemaIfNeeded()
    
    databaseDirectory = slicer.dicomDatabase.databaseDirectory
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

    # Instantiate and connect widgets ...
    if 'IDCBrowser' in slicer.util.moduleNames():
      self.modulePath = slicer.modules.idcbrowser.path.replace("IDCBrowser.py", "")
    else:
      self.modulePath = '.'
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

    #
    # Update required area
    #
    self.updateRequiredWidget = qt.QWidget()
    self.updateRequiredWidget.setLayout(qt.QGridLayout())
    self.layout.addWidget(self.updateRequiredWidget)

    self.updateRequiredLabel = qt.QLabel("Required Python libraries are outdated. Please restart Slicer to update them.")
    self.updateRequiredWidget.layout().addWidget(self.updateRequiredLabel, 0, 0, 1, 2)

    self.updateAndRestartButton = qt.QPushButton("Restart")
    self.updateAndRestartButton.toolTip = "Update required Python libraries and restart Slicer."
    self.updateAndRestartButton.connect('clicked(bool)', slicer.util.restart)
    self.updateRequiredWidget.layout().addWidget(self.updateAndRestartButton, 1, 1)

    self.updateRequiredWidget.setStyleSheet("background-color: #fffacd; color: black;")
    self.updateUpgradeRequiredWidget()

    #
    # Browser Area
    #
    browserCollapsibleButton = ctk.ctkCollapsibleButton()
    browserCollapsibleButton.text = "SlicerIDCBrowser | NCI Imaging Data Commons data release " + self.logic.idc_version
    self.layout.addWidget(browserCollapsibleButton)
    browserLayout = qt.QVBoxLayout(browserCollapsibleButton)

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

    #
    # Show Browser Button
    #
    self.showBrowserButton = qt.QPushButton("Show Browser")
    # self.showBrowserButton.toolTip = "."
    self.showBrowserButton.enabled = False
    browserLayout.addWidget(self.showBrowserButton)

    # Browser Widget Layout within the collapsible button
    browserWidgetLayout = qt.QVBoxLayout(self.browserWidget)

    self.collectionsCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.collectionsCollapsibleGroupBox.setTitle('Collections')
    browserWidgetLayout.addWidget(self.collectionsCollapsibleGroupBox)  #
    collectionsFormLayout = qt.QHBoxLayout(self.collectionsCollapsibleGroupBox)

    #
    # Manifest Downloader Area
    #
    downloaderCollapsibleButton = ctk.ctkCollapsibleButton()
    downloaderCollapsibleButton.text = "IDC Portal manifest downloader"
    self.layout.addWidget(downloaderCollapsibleButton)
    downloaderLayout = qt.QGridLayout(downloaderCollapsibleButton)

    comment = qt.QTextEdit()
    
    # Add hyperlink
    comment.append("You can use this section of the module to download data from Imaging Data Commons based on your selection in <a href=\"http://imaging.datacommons.cancer.gov\">IDC Portal</a>. Populate any of the fields below to download data based on your selection: download manifest created using IDC Portal, or PatientID, StudyInstanceUID or SeriesInstanceUID.<br>")
    comment.setReadOnly(True)

    downloaderLayout.addWidget(comment, 0, 0, 1, 4)

    # TODO: add automatic check for the validity of the entered text

    # add manifest file selector
    label = qt.QLabel('s5cmd manifest:')
    self.manifestSelector = ctk.ctkPathLineEdit()
    self.downloadFromManifestButton = qt.QPushButton("D")
    self.downloadAndIndexFromManifestButton = qt.QPushButton("DI")
    downloaderLayout.addWidget(label, 1, 0)
    downloaderLayout.addWidget(self.manifestSelector, 1, 1)
    #downloaderLayout.addWidget(self.downloadFromManifestButton, 1, 2)
    #downloaderLayout.addWidget(self.downloadAndIndexFromManifestButton, 1, 3)

    # add download by PatientID
    label = qt.QLabel('PatientID:')
    self.patientIDSelector = qt.QLineEdit()
    self.patientIDSelector.setPlaceholderText('Enter PatientID here')
    self.downloadFromPatientIDButton = qt.QPushButton("D")
    self.downloadAndIndexFromPatientIDButton = qt.QPushButton("DI")
    downloaderLayout.addWidget(label, 2, 0)
    downloaderLayout.addWidget(self.patientIDSelector, 2, 1)
    #downloaderLayout.addWidget(self.downloadFromPatientIDButton, 2, 2)
    #downloaderLayout.addWidget(self.downloadAndIndexFromPatientIDButton, 2, 3)

    # add download by StudyInstanceUID
    label = qt.QLabel('StudyInstanceUID:')
    self.studyUIDSelector = qt.QLineEdit()
    self.studyUIDSelector.setPlaceholderText('Enter DICOM StudyInstanceUID here')
    self.downloadFromStudyUIDButton = qt.QPushButton("D")
    self.downloadAndIndexFromStudyUIDButton = qt.QPushButton("DI")
    downloaderLayout.addWidget(label, 3, 0)
    downloaderLayout.addWidget(self.studyUIDSelector, 3, 1)
    #downloaderLayout.addWidget(self.downloadFromStudyUIDButton, 3, 2)
    #downloaderLayout.addWidget(self.downloadAndIndexFromStudyUIDButton, 3, 3)

    # add download by SeriesInstanceUID
    label = qt.QLabel('SeriesInstanceUID:')
    self.seriesUIDSelector = qt.QLineEdit()
    self.seriesUIDSelector.setPlaceholderText('Enter DICOM SeriesInstanceUID here')
    self.downloadFromSeriesUIDButton = qt.QPushButton("D")
    self.downloadAndIndexFromSeriesUIDButton = qt.QPushButton("DI")
    downloaderLayout.addWidget(label, 4, 0)
    downloaderLayout.addWidget(self.seriesUIDSelector, 4, 1)
    #downloaderLayout.addWidget(self.downloadFromSeriesUIDButton, 4, 2)
    #downloaderLayout.addWidget(self.downloadAndIndexFromSeriesUIDButton, 4, 3)

    # add output directory selector
    label = qt.QLabel('Download directory:')
    self.downloadDestinationSelector = ctk.ctkDirectoryButton()
    self.downloadDestinationSelector.caption = 'Output directory'
    self.downloadDestinationSelector.directory = self.storagePath
    downloaderLayout.addWidget(label, 5, 0)
    downloaderLayout.addWidget(self.downloadDestinationSelector, 5, 1, 1, 3)

    self.download_status = qt.QLabel('Download status: Ready')
    downloaderLayout.addWidget(self.download_status, 6, 0)

    #
    # Show Download Button
    #
    self.downloadButton = ctk.ctkMenuButton()
    self.downloadButton.text = "Download, import and load into scene"
    downloadButtonMenu = qt.QMenu("Download options", self.downloadButton)
    self.downloadButton.setMenu(downloadButtonMenu)

    self.importOnDownloadAction = qt.QAction("Import downloaded files to DICOM database", downloadButtonMenu)
    self.importOnDownloadAction.setToolTip("If enabled, all downloaded files are imported into the DICOM database.")
    self.importOnDownloadAction.setCheckable(True)  
    self.importOnDownloadAction.setChecked(True)
    downloadButtonMenu.addAction(self.importOnDownloadAction)  

    
    self.loadOnDownloadAction = qt.QAction("Open downloaded series", downloadButtonMenu)
    self.loadOnDownloadAction.setToolTip("If enabled, all downloaded files are imported into the DICOM database and loaded into the scene.")
    self.loadOnDownloadAction.setCheckable(False)  
    self.loadOnDownloadAction.setChecked(False)
    #downloadButtonMenu.addAction(self.loadOnDownloadAction)  
    self.onDownloadOptionsToggled(False)

    downloaderLayout.addWidget(self.downloadButton, 7,0,1,3)

    #
    # Collection Selector ComboBox
    #
    self.collectionSelectorLabel = qt.QLabel('Select collection:')
    collectionsFormLayout.addWidget(self.collectionSelectorLabel)
    # Selector ComboBox
    self.collectionSelector = qt.QComboBox()
    self.collectionSelector.setMinimumWidth(200)
    collectionsFormLayout.addWidget(self.collectionSelector)

    collectionsFormLayout.addStretch(4)
    logoLabelText = "IDC release "+self.logic.idc_version
    self.logoLabel = qt.QLabel(logoLabelText)
    collectionsFormLayout.addWidget(self.logoLabel)
    
    #Patient Table Widget
    
    self.patientsCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.patientsCollapsibleGroupBox.setTitle('Patients')
    browserWidgetLayout.addWidget(self.patientsCollapsibleGroupBox)
    patientsVBoxLayout1 = qt.QVBoxLayout(self.patientsCollapsibleGroupBox)
    patientsExpdableArea = ctk.ctkExpandableWidget()
    patientsVBoxLayout1.addWidget(patientsExpdableArea)
    patientsVBoxLayout2 = qt.QVBoxLayout(patientsExpdableArea)
    # patientsVerticalLayout = qt.QVBoxLayout(patientsExpdableArea)
    self.patientsTableWidget = qt.QTableWidget()
    self.patientsModel = qt.QStandardItemModel()
    self.patientsTableHeaderLabels = ['Patient ID', 'Patient Sex', 'Patient Age']
    self.patientsTableWidget.setColumnCount(3)
    self.patientsTableWidget.sortingEnabled = True
    self.patientsTableWidget.setHorizontalHeaderLabels(self.patientsTableHeaderLabels)
    self.patientsTableWidgetHeader = self.patientsTableWidget.horizontalHeader()
    self.patientsTableWidgetHeader.setStretchLastSection(True)
    # patientsTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
    patientsVBoxLayout2.addWidget(self.patientsTableWidget)
    self.patientsTreeSelectionModel = self.patientsTableWidget.selectionModel()
    abstractItemView = qt.QAbstractItemView()
    self.patientsTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    verticalheader = self.patientsTableWidget.verticalHeader()
    verticalheader.setDefaultSectionSize(20)
    patientsVBoxLayout1.setSpacing(0)
    patientsVBoxLayout2.setSpacing(0)
    patientsVBoxLayout1.setMargin(0)
    patientsVBoxLayout2.setContentsMargins(7, 3, 7, 7)

    #
    # Studies Table Widget
    #
    self.studiesCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.studiesCollapsibleGroupBox.setTitle('Studies')
    browserWidgetLayout.addWidget(self.studiesCollapsibleGroupBox)
    studiesVBoxLayout1 = qt.QVBoxLayout(self.studiesCollapsibleGroupBox)
    studiesExpdableArea = ctk.ctkExpandableWidget()
    studiesVBoxLayout1.addWidget(studiesExpdableArea)
    studiesVBoxLayout2 = qt.QVBoxLayout(studiesExpdableArea)
    self.studiesTableWidget = qt.QTableWidget()
    self.studiesTableWidget.setCornerButtonEnabled(True)
    self.studiesModel = qt.QStandardItemModel()
    self.studiesTableHeaderLabels = ['Study Instance UID', 'Study Date', 'Study Description', 'Series Count']
    self.studiesTableWidget.setColumnCount(4)
    self.studiesTableWidget.sortingEnabled = True
    self.studiesTableWidget.hideColumn(0)
    self.studiesTableWidget.setHorizontalHeaderLabels(self.studiesTableHeaderLabels)
    self.studiesTableWidget.resizeColumnsToContents()
    studiesVBoxLayout2.addWidget(self.studiesTableWidget)
    self.studiesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.studiesTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    studiesVerticalheader = self.studiesTableWidget.verticalHeader()
    studiesVerticalheader.setDefaultSectionSize(20)
    self.studiesTableWidgetHeader = self.studiesTableWidget.horizontalHeader()
    self.studiesTableWidgetHeader.setStretchLastSection(True)

    studiesSelectOptionsWidget = qt.QWidget()
    studiesSelectOptionsLayout = qt.QHBoxLayout(studiesSelectOptionsWidget)
    studiesSelectOptionsLayout.setMargin(0)
    studiesVBoxLayout2.addWidget(studiesSelectOptionsWidget)
    studiesSelectLabel = qt.QLabel('Select:')
    studiesSelectOptionsLayout.addWidget(studiesSelectLabel)
    self.studiesSelectAllButton = qt.QPushButton('All')
    self.studiesSelectAllButton.enabled = False
    self.studiesSelectAllButton.setMaximumWidth(50)
    studiesSelectOptionsLayout.addWidget(self.studiesSelectAllButton)
    self.studiesSelectNoneButton = qt.QPushButton('None')
    self.studiesSelectNoneButton.enabled = False
    self.studiesSelectNoneButton.setMaximumWidth(50)
    studiesSelectOptionsLayout.addWidget(self.studiesSelectNoneButton)
    studiesSelectOptionsLayout.addStretch(1)
    studiesVBoxLayout1.setSpacing(0)
    studiesVBoxLayout2.setSpacing(0)
    studiesVBoxLayout1.setMargin(0)
    studiesVBoxLayout2.setContentsMargins(7, 3, 7, 7)

    #
    # Series Table Widget
    #
    self.seriesCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.seriesCollapsibleGroupBox.setTitle('Series')
    browserWidgetLayout.addWidget(self.seriesCollapsibleGroupBox)
    seriesVBoxLayout1 = qt.QVBoxLayout(self.seriesCollapsibleGroupBox)
    seriesExpdableArea = ctk.ctkExpandableWidget()
    seriesVBoxLayout1.addWidget(seriesExpdableArea)
    seriesVBoxLayout2 = qt.QVBoxLayout(seriesExpdableArea)
    self.seriesTableWidget = qt.QTableWidget()
    # self.seriesModel = qt.QStandardItemModel()
    self.seriesTableWidget.setColumnCount(10)
    self.seriesTableWidget.sortingEnabled = True
    self.seriesTableWidget.hideColumn(0)
    self.seriesTableHeaderLabels = ['Series Instance UID', 'Status', 'Modality',
                    'Series Date', 'Series Description', 'Body Part Examined',
                    'Series Number','Manufacturer',
                    'Manufacturer Model Name','Instance Count']
    self.seriesTableWidget.setHorizontalHeaderLabels(self.seriesTableHeaderLabels)
    self.seriesTableWidget.resizeColumnsToContents()
    seriesVBoxLayout2.addWidget(self.seriesTableWidget)
    self.seriesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.seriesTableWidget.setSelectionBehavior(abstractItemView.SelectRows)
    self.seriesTableWidget.setSelectionMode(3)
    self.seriesTableWidgetHeader = self.seriesTableWidget.horizontalHeader()
    self.seriesTableWidgetHeader.setStretchLastSection(True)
    # seriesTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
    seriesVerticalheader = self.seriesTableWidget.verticalHeader()
    seriesVerticalheader.setDefaultSectionSize(20)

    seriesSelectOptionsWidget = qt.QWidget()
    seriesSelectOptionsLayout = qt.QHBoxLayout(seriesSelectOptionsWidget)
    seriesVBoxLayout2.addWidget(seriesSelectOptionsWidget)
    seriesSelectOptionsLayout.setMargin(0)
    seriesSelectLabel = qt.QLabel('Select:')
    seriesSelectOptionsLayout.addWidget(seriesSelectLabel)
    self.seriesSelectAllButton = qt.QPushButton('All')
    self.seriesSelectAllButton.enabled = False
    self.seriesSelectAllButton.setMaximumWidth(50)
    seriesSelectOptionsLayout.addWidget(self.seriesSelectAllButton)
    self.seriesSelectNoneButton = qt.QPushButton('None')
    self.seriesSelectNoneButton.enabled = False
    self.seriesSelectNoneButton.setMaximumWidth(50)
    seriesSelectOptionsLayout.addWidget(self.seriesSelectNoneButton)
    seriesVBoxLayout1.setSpacing(0)
    seriesVBoxLayout2.setSpacing(0)
    seriesVBoxLayout1.setMargin(0)
    seriesVBoxLayout2.setContentsMargins(7, 3, 7, 7)

    seriesSelectOptionsLayout.addStretch(1)
    self.imagesCountLabel = qt.QLabel()
    self.imagesCountLabel.text = 'No. of images to download: ' + '<span style=" font-size:8pt; font-weight:600; ' \
                    'color:#aa0000;">' + str(self.imagesToDownloadCount) + '</span>' + ' '
    seriesSelectOptionsLayout.addWidget(self.imagesCountLabel)
    # seriesSelectOptionsLayout.setAlignment(qt.Qt.AlignTop)

    # Index Button
    #
    self.indexButton = qt.QPushButton()
    self.indexButton.setMinimumWidth(50)
    self.indexButton.toolTip = "Download and Index: The browser will download" \
                   " the selected series and index them in 3D Slicer DICOM Database."
    self.indexButton.setIcon(downloadAndIndexIcon)
    iconSize = qt.QSize(70, 40)
    self.indexButton.setIconSize(iconSize)
    # self.indexButton.setMinimumHeight(50)
    self.indexButton.enabled = False
    # downloadWidgetLayout.addStretch(4)
    seriesSelectOptionsLayout.addWidget(self.indexButton)

    # downloadWidgetLayout.addStretch(1)
    #
    # Load Button
    #
    self.loadButton = qt.QPushButton("")
    self.loadButton.setMinimumWidth(50)
    self.loadButton.setIcon(downloadAndLoadIcon)
    self.loadButton.setIconSize(iconSize)
    # self.loadButton.setMinimumHeight(50)
    self.loadButton.toolTip = "Download and Load: The browser will download" \
                  " the selected series and Load them in 3D Slicer scene."
    self.loadButton.enabled = False
    seriesSelectOptionsLayout.addWidget(self.loadButton)
    # downloadWidgetLayout.addStretch(4)

    self.cancelDownloadButton = qt.QPushButton('')
    seriesSelectOptionsLayout.addWidget(self.cancelDownloadButton)
    self.cancelDownloadButton.setIconSize(iconSize)
    self.cancelDownloadButton.toolTip = "Cancel all downloads."
    self.cancelDownloadButton.setIcon(cancelIcon)
    self.cancelDownloadButton.enabled = False

    self.statusFrame = qt.QFrame()
    browserWidgetLayout.addWidget(self.statusFrame)
    statusHBoxLayout = qt.QHBoxLayout(self.statusFrame)
    statusHBoxLayout.setMargin(0)
    statusHBoxLayout.setSpacing(0)
    self.statusLabel = qt.QLabel('')
    statusHBoxLayout.addWidget(self.statusLabel)
    statusHBoxLayout.addStretch(1)
  
    #
    # delete data context menu
    #
    self.seriesTableWidget.setContextMenuPolicy(2)
    self.removeSeriesAction = qt.QAction("Remove from disk", self.seriesTableWidget)
    self.seriesTableWidget.addAction(self.removeSeriesAction)
    # self.removeSeriesAction.enabled = False

    #
    # Settings Area
    #
    settingsCollapsibleButton = ctk.ctkCollapsibleButton()
    settingsCollapsibleButton.text = "Settings"
    self.layout.addWidget(settingsCollapsibleButton)
    settingsGridLayout = qt.QGridLayout(settingsCollapsibleButton)
    settingsCollapsibleButton.collapsed = True

    # Storage Path button
    #
    # storageWidget = qt.QWidget()
    # storageFormLayout = qt.QFormLayout(storageWidget)
    # settingsVBoxLayout.addWidget(storageWidget)

    storagePathLabel = qt.QLabel("Storage Folder: ")
    self.storagePathButton = ctk.ctkDirectoryButton()
    self.storagePathButton.directory = self.storagePath
    self.storageResetButton = qt.QPushButton("Reset Path")
    self.storageResetButton.toolTip = "Resetting the storage folder to default."
    self.storageResetButton.enabled  = True if self.settings.contains("IDCCustomStoragePath") else False
    settingsGridLayout.addWidget(storagePathLabel, 0, 0, 1, 1)
    settingsGridLayout.addWidget(self.storagePathButton, 0, 1, 1, 2)
    settingsGridLayout.addWidget(self.storageResetButton, 0, 3, 1, 1)

    # connections
    self.showBrowserButton.connect('clicked(bool)', self.onShowBrowserButton)
    self.downloadButton.connect('clicked(bool)', self.onDownloadButton)
    self.collectionSelector.connect('currentIndexChanged(QString)', self.collectionSelected)
    self.patientsTableWidget.connect('itemSelectionChanged()', self.patientsTableSelectionChanged)
    self.studiesTableWidget.connect('itemSelectionChanged()', self.studiesTableSelectionChanged)
    self.seriesTableWidget.connect('itemSelectionChanged()', self.seriesSelected)
    #self.useCacheCeckBox.connect('stateChanged(int)', self.onUseCacheStateChanged)
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

    self.loadOnDownloadAction.connect('toggled(bool)', self.onDownloadOptionsToggled)
    self.importOnDownloadAction.connect('toggled(bool)', self.onDownloadOptionsToggled)

    # Add vertical spacer
    self.layout.addStretch(1)

    if self.showBrowserButton != None and self.showBrowserButton.enabled:
      self.showBrowser()
    if not self.initialConnection:
      self.getCollectionValues()

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

  def cleanup(self):
    pass

  def onDownloadOptionsToggled(self, state):
    importState = self.importOnDownloadAction.isChecked()
    loadState = self.loadOnDownloadAction.isChecked()

    buttonLabel = "Download"
    if importState:
      if loadState:
        buttonLabel = buttonLabel + ", import and load into scene"
      else:
        buttonLabel = buttonLabel + " and import into DICOM database"

    self.downloadButton.text = buttonLabel

  def onShowBrowserButton(self):
    self.showBrowser()

  # TODO: goes to logic
  def downloadFromQuery(self, query, downloadDestination):
    logging.debug("Downloading from query: " + query)
    manifest_path = os.path.join(downloadDestination,'manifest.csv')
    manifest_df = self.IDCClient.sql_query(query)
    manifest_df.to_csv(manifest_path, index=False, header=False)
    logging.info("Will download to "+downloadDestination)
    self.IDCClient.download_from_manifest(manifest_path, downloadDestination)

  def onDownloadButton(self):

    startTime = time.time()
    self.download_status.setText('Download status: Downloading...')
    slicer.app.processEvents()
    import os
    if(os.path.exists(self.manifestSelector.currentPath)):
      self.download_status.setText('Downloading from manifest...')
      try:
        self.IDCClient.download_from_manifest(self.manifestSelector.currentPath, self.downloadDestinationSelector.directory)
      except Exception as error:
        self.download_status.setText('Download from manifest failed.')
        logging.error('Download from manifest failed.')
        logging.error(error)
        return
      self.download_status.setText('Download from manifest done.')

    if(self.patientIDSelector.text != ''):
      # TODO: how to interrupt long download from GUI?
      self.download_status.setText('Downloading from PatientID...')
      query = """
        SELECT CONCAT('cp ',series_aws_url,' .')
        FROM index
        WHERE PatientID = '""" + self.patientIDSelector.text + """'
      """
      try:
        self.downloadFromQuery(query, self.downloadDestinationSelector.directory)
      except Exception as error:
        self.download_status.setText('Download from PatientID failed.')
        logging.error('Download from PatientID failed.')
        logging.error(error)
        return
      self.download_status.setText('Download from PatientID done.')

    if(self.studyUIDSelector.text != ''):
      # TODO: how to interrupt long download from GUI?
      self.download_status.setText('Downloading from StudyInstanceUID...')
      query = """
        SELECT CONCAT('cp ',series_aws_url,' .')
        FROM index
        WHERE StudyInstanceUID = '""" + self.studyUIDSelector.text + """'
      """
      try:
        self.downloadFromQuery(query, self.downloadDestinationSelector.directory)
      except Exception as error:
        self.download_status.setText('Download from StudyInstanceUID failed.')
        logging.error('Download from StudyInstanceUID failed.')
        logging.error(error)
        return
      self.download_status.setText('Download from StudyInstanceUID done.')

    if(self.seriesUIDSelector.text != ''):
      # TODO: how to interrupt long download from GUI?
      self.download_status.setText('Downloading from SeriesInstanceUID...')
      query = """
        SELECT CONCAT('cp ',series_aws_url,' .')
        FROM index
        WHERE SeriesInstanceUID = '""" + self.seriesUIDSelector.text + """'
      """
      try:
        self.downloadFromQuery(query, self.downloadDestinationSelector.directory)
      except Exception as error:
        self.download_status.setText('Download from SeriesInstanceUID failed.')
        logging.error('Download from SeriesInstanceUID failed.')
        logging.error(error)
        return
      self.download_status.setText('Download from SeriesInstanceUID done.')

    self.download_status.setText('Download status: Done in {0:.2f} seconds.'.format(time.time() - startTime))
    logging.info('Download status: Done in {0:.2f} seconds.'.format(time.time() - startTime))

    if self.importOnDownloadAction.isChecked():
      logging.info('Importing downloaded data into DICOM database ...')
      self.download_status.setText('Importing downloaded data into DICOM database ...')
      self.addFilesToDatabase(self.downloadDestinationSelector.directory)
      self.download_status.setText('Importing downloaded data into DICOM database done.')
      logging.info('Importing downloaded data into DICOM database done.')

    if self.loadOnDownloadAction.isChecked():
      logging.info('Loading downloaded data into scene ...')
      self.download_status.setText('Loading downloaded data into scene ...')
      self.logic.loadData(self.downloadDestinationSelector.directory)
      self.download_status.setText('Loading downloaded data into scene done.')
      logging.info('Loading downloaded data into scene done.')
 
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
    if not self.browserWidget.isVisible():
      self.popupPositioned = False
      self.browserWidget.show()
      if self.popupGeometry.isValid():
        self.browserWidget.setGeometry(self.popupGeometry)
    self.browserWidget.raise_()

    if not self.popupPositioned:
      mainWindow = slicer.util.mainWindow()
      if mainWindow is None:
        return
      screenMainPos = mainWindow.pos
      x = screenMainPos.x() + 100
      y = screenMainPos.y() + 100
      self.browserWidget.move(qt.QPoint(x, y))
      self.popupPositioned = True

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

  def onStudiesSelectAllButton(self):
    self.studiesTableWidget.selectAll()

  def onStudiesSelectNoneButton(self):
    self.studiesTableWidget.clearSelection()

  def onSeriesSelectAllButton(self):
    self.seriesTableWidget.selectAll()

  def onSeriesSelectNoneButton(self):
    self.seriesTableWidget.clearSelection()

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
    for series in self.downloadQueue.keys():
      self.removeDownloadProgressBar(series)
    downloadQueue = {}
    seriesRowNumber = {}

  def addFilesToDatabase(self, directory=None):
    self.progressMessage = "Adding Files to DICOM Database "
    self.showStatus(self.progressMessage)

    indexer = ctk.ctkDICOMIndexer()
    # DICOM indexer uses the current DICOM database folder as the basis for relative paths,
    # therefore we must convert the folder path to absolute to ensure this code works
    # even when a relative path is used as self.extractedFilesDirectory.
    if not directory:
      indexer.addDirectory(slicer.dicomDatabase, os.path.abspath(self.extractedFilesDirectory))
    else:
      indexer.addDirectory(slicer.dicomDatabase, os.path.abspath(directory))
    indexer.waitForImportFinished()
    self.clearStatus()

  def addSelectedToDownloadQueue(self):
    self.cancelDownload = False
    allSelectedSeriesUIDs = []
    downloadQueue = {}
    self.seriesRowNumber = {}

    for n in range(len(self.seriesInstanceUIDs)):
      # print self.seriesInstanceUIDs[n]
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
        #if not any(selectedSeries == s for s in self.previouslyDownloadedSeries):
        if True:
          self.makeDownloadProgressBar(selectedSeries, n)
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
          dicomDatabase = slicer.dicomDatabase
          fileList = slicer.dicomDatabase.filesForSeries(seriesUID)
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
    
    while self.downloadQueue and not self.cancelDownload:
      self.cancelDownloadButton.enabled = True
      selectedSeries, downloadFolderPath = self.downloadQueue.popitem()
      if not os.path.exists(downloadFolderPath):
        logging.debug("Creating directory to keep the downloads: " + downloadFolderPath)
        os.makedirs(downloadFolderPath)
      # save series uid in a text file for further reference
      with open(downloadFolderPath + 'seriesUID.txt', 'w') as f:
        f.write(selectedSeries)
        f.close()
      fileName = downloadFolderPath + 'images.zip'
      logging.debug("Downloading images to " + fileName)
      self.extractedFilesDirectory = downloadFolderPath
      self.progressMessage = "Downloading Images for series InstanceUID: " + selectedSeries
      self.showStatus(self.progressMessage)
      #seriesSize = self.getSeriesSize(selectedSeries)
      logging.debug(self.progressMessage)
      try:
        start_time = time.time()
        response = self.IDCClient.download_dicom_series(seriesInstanceUID=selectedSeries, downloadDir=self.extractedFilesDirectory)
        slicer.app.processEvents()
        logging.debug("Downloaded images in %s seconds" % (time.time() - start_time))

        try:
          start_time = time.time()
          self.addFilesToDatabase()
          logging.debug("Added files to database in %s seconds" % (time.time() - start_time))
          self.previouslyDownloadedSeries.append(selectedSeries)
          '''
          #          
          with open(self.downloadedSeriesArchiveFile, 'wb') as f:
            pickle.dump(self.previouslyDownloadedSeries, f)
          f.close()
          '''
          n = self.seriesRowNumber[selectedSeries]
          table = self.seriesTableWidget
          item = table.item(n, 1)
          item.setIcon(self.storedlIcon)
        except Exception as error:
          import traceback
          traceback.print_exc()
          logging.error("Failed to add images to the database!")
          self.removeDownloadProgressBar(selectedSeries)
          self.downloadQueue.pop(selectedSeries, None)


      except Exception as error:
        import traceback
        traceback.print_exc()
        self.clearStatus()
        message = "downloadSelectedSeries: Failed to download " + str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                    'SlicerIDCBrowser', message, qt.QMessageBox.Ok)
    self.cancelDownloadButton.enabled = False
    self.collectionSelector.enabled = True
    self.patientsTableWidget.enabled = True
    self.studiesTableWidget.enabled = True

  def makeDownloadProgressBar(self, selectedSeries, n):
    downloadProgressBar = qt.QProgressBar()
    self.downloadProgressBars[selectedSeries] = downloadProgressBar
    titleLabel = qt.QLabel(selectedSeries)
    progressLabel = qt.QLabel(self.selectedSeriesNicknamesDic[selectedSeries] + ' (0 KB)')
    self.downloadProgressLabels[selectedSeries] = progressLabel
    table = self.seriesTableWidget
    table.setCellWidget(n, 1, downloadProgressBar)
    # self.downloadFormLayout.addRow(progressLabel,downloadProgressBar)

  def removeDownloadProgressBar(self, selectedSeries):
    n = self.seriesRowNumber[selectedSeries]
    table = self.seriesTableWidget
    table.setCellWidget(n, 1, None)
    self.downloadProgressBars[selectedSeries].deleteLater()
    del self.downloadProgressBars[selectedSeries]
    self.downloadProgressLabels[selectedSeries].deleteLater()
    del self.downloadProgressLabels[selectedSeries]

  def stringBufferReadWrite(self, dstFile, responseString, bufferSize=819):
      dstFile.write(responseString)

  # This part was adopted from XNATSlicer module
  def __bufferReadWrite(self, dstFile, response, selectedSeries, seriesSize, bufferSize=8192):

    currentDownloadProgressBar = self.downloadProgressBars[selectedSeries]
    currentProgressLabel = self.downloadProgressLabels[selectedSeries]

    # Define the buffer read loop
    self.downloadSize = 0
    while 1:
      # If DOWNLOAD FINISHED
      buffer = response.read(bufferSize)
      slicer.app.processEvents()
      if not buffer:
        # Pop from the queue
        currentDownloadProgressBar.setMaximum(100)
        currentDownloadProgressBar.setValue(100)
        # currentDownloadProgressBar.setVisible(False)
        # currentProgressLabel.setVisible(False)
        self.removeDownloadProgressBar(selectedSeries)
        self.downloadQueue.pop(selectedSeries, None)
        break
      if self.cancelDownload:
        return False

      # Otherwise, Write buffer chunk to file
      slicer.app.processEvents()
      dstFile.write(buffer)
      #
      # And update progress indicators
      #
      self.downloadSize += len(buffer)
      currentDownloadProgressBar.setValue(self.downloadSize / seriesSize * 100)
      # currentDownloadProgressBar.setMaximum(0)
      currentProgressLabel.text = self.selectedSeriesNicknamesDic[
                      selectedSeries] + ' (' + str(int(self.downloadSize / 1024)
                                     ) + ' of ' + str(
        int(seriesSize / 1024)) + " KB)"
    # return self.downloadSize
    return True

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

      self.collectionSelector.disconnect('currentIndexChanged(QString)')
      self.collectionSelector.clear()
      self.collectionSelector.connect('currentIndexChanged(QString)', self.collectionSelected)

      n = 0  # If you intend to use the 'n' variable for a specific purpose, it's kept here.

      for name in collectionNames:
          self.collectionSelector.addItem(name)


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
    import importlib.metadata
    import importlib.util
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
  
      if slicer.util.confirmOkCancelDisplay(userMessage, "SlicerIDCIndex initialization"):
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
