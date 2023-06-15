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
        self.s5cmdPath = ''

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

        cmd = [self.s5cmdPath,'--no-sign-request','--endpoint-url','https://storage.googleapis.com','cp',series_url,downloadDir]
        #print(" ".join(cmd))
        ret = subprocess.run(cmd)

        return 0