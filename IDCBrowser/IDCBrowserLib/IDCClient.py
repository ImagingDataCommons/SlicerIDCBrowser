import json, string, os
import requests, logging
import slicer
#import TCIABrowserLib

#
# Refer https://wiki.cancerimagingarchive.net/display/Public/REST+API+Usage+Guide for complete list of API
#
class IDCClient:
    GET_IMAGE = "getImage"
    GET_MANUFACTURER_VALUES = "getManufacturerValues"
    GET_MODALITY_VALUES = "getModalityValues"
    GET_COLLECTION_VALUES = "getCollectionValues"
    GET_BODY_PART_VALUES = "getBodyPartValues"
    GET_PATIENT_STUDY = "getPatientStudy"
    GET_SERIES = "getSeries"
    GET_SERIES_SIZE = "getSeriesSize"
    GET_PATIENT = "getPatient"

    # use Slicer API key by default
    def __init__(self, baseUrl='https://api.imaging.datacommons.cancer.gov/v1'):
        self.baseUrl = baseUrl

    def execute_get(self, url, params=None, json=None):

        response = requests.get(url, params=params, json=json)
        if response.status_code != 200:
            # Print the error code and message if something went wrong
            print('Request failed: {}'.format(response.reason))

        return response

    def execute_post(self, url, params=None, json=None):

        response = requests.post(url, params=params, json=json)
        if response.status_code != 200:
            # Print the error code and message if something went wrong
            print('Request failed: {}'.format(response.reason))

        return response

    def get_modality_values(self,collection = None , bodyPartExamined = None , modality = None , outputFormat = "json" ):
        serviceUrl = self.baseUrl + "/" + self.GET_MODALITY_VALUES
        queryParameters = {"Collection" : collection , "BodyPartExamined" : bodyPartExamined , "Modality" : modality , "format" : outputFormat }
        resp = self.execute(serviceUrl , queryParameters)
        return resp

    def get_manufacturer_values(self,collection = None , bodyPartExamined = None , modality = None , outputFormat = "json" ):
        '''
        serviceUrl = self.baseUrl + "/" + self.GET_MANUFACTURER_VALUES
        queryParameters = {"Collection" : collection , "BodyPartExamined" : bodyPartExamined , "Modality" : modality , "format" : outputFormat }
        resp = self.execute(serviceUrl , queryParameters)
        '''
        return None

    def get_collection_values(self,outputFormat = "json" ):
        url = '{}/collections'.format(self.baseUrl)
        resp = self.execute_get(url)

        idc_collections = []

        for c in resp.json()['collections']:
            idc_collections.append({"Collection":c["collection_id"]})

        logging.debug("Get collections response: %s", json.dumps(idc_collections))
        return json.dumps(idc_collections)

    def get_body_part_values(self,collection = None , bodyPartExamined = None , modality = None , outputFormat = "csv" ):
        return None
        serviceUrl = self.baseUrl + "/" + self.GET_BODY_PART_VALUES
        queryParameters = {"Collection" : collection , "BodyPartExamined" : bodyPartExamined , "Modality" : modality , "format" : outputFormat }
        resp = self.execute(serviceUrl , queryParameters)
        return resp
    
    '''
    def get_patient_study(self,collection = None , patientId = None , studyInstanceUid = None , outputFormat = "json" ):
        return None
        serviceUrl = self.baseUrl + "/" + self.GET_PATIENT_STUDY
        queryParameters = {"Collection" : collection , "PatientID" : patientId , "StudyInstanceUID" : studyInstanceUid , "format" : outputFormat }
        resp = self.execute(serviceUrl , queryParameters)
        return resp
   

    def get_series(self,collection = None , patientId = None , studyInstanceUID = None, modality = None , outputFormat = "json" ):
        return None
        serviceUrl = self.baseUrl + "/" + self.GET_SERIES
        queryParameters = {"Collection" : collection , "PatientID" : patientId ,"StudyInstanceUID": studyInstanceUID, "Modality" : modality , "format" : outputFormat }
        resp = self.execute(serviceUrl , queryParameters)
        return resp
    '''
    def get_series_size(self, seriesInstanceUid ):
        return None
        serviceUrl = self.baseUrl + "/" + self.GET_SERIES_SIZE
        queryParameters = { "SeriesInstanceUID" : seriesInstanceUid }
        resp = self.execute(serviceUrl , queryParameters)
        return resp
    


    def get_patient(self,collection = None , outputFormat = "json" ):
        filters = {
            "collection_id": [collection],
        }
        cohortSpec = {"name": "testcohort",
              "description": "Test description",
              "filters": filters}
        params = dict(
            sql = False,
            Collection_ID = True,
            Patient_ID = True,
            page_size = 2000
        )
        url = '{}/cohorts/manifest/preview'.format(self.baseUrl)
        resp = self.execute_post(url , params=params, json=cohortSpec)

        idc_json = resp.json()['manifest']['json_manifest']

        idc_response = []

        for idc_item in idc_json:
            print(idc_item)
            idc_item = {"PatientID":idc_item['Patient_ID'], 'PatientName':'', 'PatientSex':'', 'Collection':idc_item['Collection_ID']}
            idc_response.append(idc_item)

        logging.debug("Get patient response: %s", json.dumps(idc_response))

        return json.dumps(idc_response)
    
    def get_patient_study(self,collection = None , patientId = None , studyInstanceUid = None , outputFormat = "json" ):

        filters = {
            "PatientID": [patientId],
        }
        cohortSpec = {"name": "testcohort",
              "description": "Test description",
              "filters": filters}
        params = dict(
            sql = False,
            Collection_ID = True,
            Patient_ID = False,
            StudyInstanceUID = True,
            page_size = 2000
        )
        url = '{}/cohorts/manifest/preview'.format(self.baseUrl)
        resp = self.execute_post(url , params=params, json=cohortSpec)

        idc_json = resp.json()['manifest']['json_manifest']

        idc_response = []
        for idc_item in idc_json:
            idc_item = {'Collection':idc_item['Collection_ID'], \
                    'PatientID':patientId, \
                    'PatientName':'', \
                    'PatientSex':'', \
                    'StudyInstanceUID':idc_item['StudyInstanceUID'],\
                    'StudyDate':'',\
                    'StudyDescription':'',\
                    'PatientAge':'',\
                    'SeriesCount': ''\
                    }
            idc_response.append(idc_item)

        logging.debug("Get study response: %s", json.dumps(idc_response))

        return json.dumps(idc_response)

    def get_series(self,collection = None , patientId = None , studyInstanceUID = None, modality = None , outputFormat = "json" ):
        filters = {
            "StudyInstanceUID": [studyInstanceUID],
        }
        cohortSpec = {"name": "testcohort",
              "description": "Test description",
              "filters": filters}
        params = dict(
            sql = False,
            Collection_ID = True,
            Patient_ID = False,
            StudyInstanceUID = False,
            SeriesInstanceUID = True,
            page_size = 2000
        )
        url = '{}/cohorts/manifest/preview'.format(self.baseUrl)
        resp = self.execute_post(url , params=params, json=cohortSpec)

        idc_json = resp.json()['manifest']['json_manifest']

        idc_response = []
        for idc_item in idc_json:
            idc_item = {'SeriesInstanceUID':idc_item['SeriesInstanceUID'],\
                    'StudyInstanceUID':studyInstanceUID,\
                    'Modality':'',\
                    'SeriesDate':'',\
                    'SeriesDescription':'',\
                    'SeriesNumber':'',\
                    'Collection':idc_item['Collection_ID'], \
                    'Manufacturer':'',\
                    'ManufacturerModelName':'',\
                    'SoftwareVersions':'',\
                    'Visibility':'1',\
                    'ImageCount':'1'\
                    }
            idc_response.append(idc_item)
        logging.debug("Get series response: %s", json.dumps(idc_response))
        return json.dumps(idc_response)

    def get_image(self , seriesInstanceUid, downloadDir):
        filters = {
            "SeriesInstanceUID": [seriesInstanceUid],
        }
        cohortSpec = {"name": "testcohort",
              "description": "Test description",
              "filters": filters}
        params = dict(
            sql = False,
            Collection_ID = False,
            Patient_ID = False,
            StudyInstanceUID = False,
            SeriesInstanceUID = True,
            GCS_URL = True,
            page_size = 1
        )
        url = '{}/cohorts/manifest/preview'.format(self.baseUrl)
        resp = self.execute_post(url , params=params, json=cohortSpec)
        
        gcs_url = resp.json()['manifest']['json_manifest'][0]['GCS_URL']

        series_url = 's3'+gcs_url[2:gcs_url.rfind('/')+1]+'*'
        
        #if not self.iss5cmdPathValid():
        #    self.setups5cmd()

        import subprocess

        cmd = ['/usr/local/bin/s5cmd','--no-sign-request','--endpoint-url','https://storage.googleapis.com','cp',series_url,downloadDir]
        #print(" ".join(cmd))
        ret = subprocess.run(cmd)

        return 0

    # inherited from 
    # https://github.com/Slicer/Slicer/blob/main/Modules/Scripted/ScreenCapture/ScreenCapture.py#L873

    def setups5cmd(self):
        self.findFfmpeg()
        if not self.isFfmpegPathValid():
            # ffmpeg not found, offer downloading it
            if slicer.util.confirmOkCancelDisplay(
                's5cmd download tool is not detected on your system. '
                'Download s5cmd?',
                    windowTitle='Download confirmation'):
                if not self.s5cmdDownload():
                    slicer.util.errorDisplay("s5cmd download failed")
        if not self.logic.iss5cmdPathValid():
            return False
        self.s5cmdPathSelector.currentPath = self.gets5cmdPath()

    def iss5cmdPathValid(self):
        s5cmdPath = self.get5cmdPath()
        return os.path.isfile(s5cmdPath)
    
    def getDownloadeds5cmdDirectory(self):
        return os.path.dirname(slicer.app.slicerUserSettingsFilePath) + '/s5cmd'

    def gets5cmdExecutableFilename(self):
        if os.name == 'nt':
            return 's5cmd.exe'
        elif os.name == 'posix':
            return 's5cmd'
        else:
            return None

    def finds5cmd(self):
        # Try to find the executable at specific paths
        commons5cmdPaths = [
            '/usr/local/bin/s5cmd',
            '/usr/bin/s5cmd'
        ]
        for s5cmdPath in commons5cmdPaths:
            if os.path.isfile(s5cmdPath):
                # found one
                self.sets5cmdPath(s5cmdPath)
                return True
        # Search for the executable in directories
        commons5cmdDirs = [
            self.getDownloadeds5cmdDirectory()
        ]
        for s5cmdDir in commons5cmdDirs:
            if self.finds5cmdInDirectory(s5cmdDir):
                # found it
                return True
        # Not found
        return False
    
    def finds5cmdInDirectory(self, s5cmdDir):
        s5cmdExecutableFilename = self.gets5cmdExecutableFilename()
        for dirpath, dirnames, files in os.walk(s5cmdDir):
            for name in files:
                if name == s5cmdExecutableFilename:
                    s5cmdExecutablePath = (dirpath + '/' + name).replace('\\', '/')
                    self.sets5cmdPath(s5cmdExecutablePath)
                    return True
        return False
    
    def unzips5cmd(self, filePath, s5cmdTargetDirectory):
        if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
            logging.info('s5cmd package is not found at ' + filePath)
            return False

        logging.info('Unzipping s5cmd package ' + filePath)
        qt.QDir().mkpath(s5cmdTargetDirectory)
        slicer.app.applicationLogic().Unzip(filePath, s5cmdTargetDirectory)
        success = self.finds5cmdInDirectory(s5cmdTargetDirectory)
        return success

    def s5cmdDownload(self):
        s5cmdTargetDirectory = self.getDownloadeds5cmdDirectory()
        # The number in the filePath can be incremented each time a significantly different s5cmd version
        # is to be introduced (it prevents reusing a previously downloaded package).
        filePath = slicer.app.temporaryPath + '/s5cmd-package-slicer-01.zip'
        success = self.unzips5cmd(filePath, s5cmdTargetDirectory)
        if success:
            # there was a valid downloaded package already
            return True

        # List of mirror sites to attempt download s5cmd pre-built binaries from
        urls = []
        if os.name == 'nt':
            urls.append('hhttps://github.com/peak/s5cmd/releases/download/v2.0.0/s5cmd_2.0.0_Windows-64bit.zip')
        elif os.name == 'posix':
            urls.append('https://github.com/peak/s5cmd/releases/download/v2.0.0/s5cmd_2.0.0_macOS-64bit.tar.gz')
        else:
            # TODO: implement downloading for other platforms?
            pass

        success = False
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

        for url in urls:

            success = True
            try:
                logging.info('Requesting download s5cmd from %s...' % url)
                import urllib.request, urllib.error, urllib.parse
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                data = urllib.request.urlopen(req).read()
                with open(filePath, "wb") as f:
                    f.write(data)

                success = self.unzips5cmd(filePath, s5cmdTargetDirectory)
            except:
                success = False

            if success:
                break

        qt.QApplication.restoreOverrideCursor()
        return success

    def gets5cmdPath(self):
        settings = qt.QSettings()
        if settings.contains('General/s5cmdPath'):
            return slicer.app.toSlicerHomeAbsolutePath(settings.value('General/s5cmdPath'))
        return ''

    def sets5cmdPath(self, s5cmdPath):
        # don't save it if already saved
        settings = qt.QSettings()
        if settings.contains('General/s5cmdPath'):
            if s5cmdPath == slicer.app.toSlicerHomeAbsolutePath(settings.value('General/s5cmdPath')):
                return
        settings.setValue('General/s5cmdPath', slicer.app.toSlicerHomeRelativePath(s5cmdPath))

