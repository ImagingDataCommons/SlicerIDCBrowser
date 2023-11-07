#
# Copyright 2015-2021, Institute for Systems Biology
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import json, string, os
import requests, logging
import pandas as pd

# import TCIABrowserLib

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
    def __init__(self, csv_index_path='https://github.com/vkt1414/SlicerIDCBrowser/releases/download/v0.0.2/index_v2.csv'): 
        self.s5cmdPath = None
        self.index = pd.read_csv(csv_index_path,dtype={14: str, 15: str})
        self.index = self.index.astype(str).replace('nan', '')


    def get_collection_values(self, outputFormat="list"):
        # Use the DataFrame to get unique collection IDs
        unique_collections = self.index['collection_id'].unique()
        return unique_collections.tolist()


    def get_series_size(self, seriesInstanceUid):
        resp = self.index[['SeriesInstanceUID']==seriesInstanceUid]['series_size_MB'].iloc[0]
        return resp

    def get_patient(self, collection=None, outputFormat="json"):
        if collection is not None:
            print(collection)
            patient_df = self.index[self.index['collection_id'] == collection].copy()  # Make a copy

        else:
            patient_df = self.index.copy()  # Make a copy
            #patient_df = self.index[self.index['collection_id'] == 'nsclc_radiomics'].copy() 
        #patient_df['patient_size_MB'] = patient_df.groupby('PatientID')['series_size_MB'].transform('sum')
        #patient_df['patient_study_count'] = patient_df.groupby('PatientID')['StudyInstanceUID'].transform('count')
        #patient_df['patient_series_count'] = patient_df.groupby('PatientID')['SeriesInstanceUID'].transform('count')
        #patient_df['patient_instance_count'] = patient_df.groupby('PatientID')['instanceCount'].transform('count')

        patient_df=patient_df.rename(columns={'collection_id':'Collection'})
        patient_df = patient_df[['PatientID', 'PatientSex', 'PatientAge']]
        patient_df = patient_df.groupby('PatientID').agg({
            'PatientSex': lambda x: ','.join(x[x != ''].unique()),
            'PatientAge': lambda x: ','.join(x[x != ''].unique())
        }).reset_index()

        patient_df = patient_df.drop_duplicates().sort_values(by='PatientID')
        # Convert DataFrame to a list of dictionaries for the API-like response
        idc_response = patient_df.to_dict(orient="records")

        logging.debug("Get patient response: %s", str(idc_response))

        return idc_response

    
    def get_patient_study(self, collection=None, patientId=None, studyInstanceUid=None, outputFormat="json"):
        if collection is not None:
            patient_study_df = self.index[self.index['collection_id'] == collection].copy()  # Make a copy
        elif patientId is not None:
            patient_study_df = self.index[self.index['PatientID'] == patientId].copy()  # Make a copy
        elif studyInstanceUid is not None:
            patient_study_df = self.index[self.index['StudyInstanceUID'] == studyInstanceUid].copy()  # Make a copy
        else:
            patient_study_df = self.index.copy()  # Make a copy

        patient_study_df['patient_study_size_MB'] = patient_study_df.groupby(['PatientID', 'StudyInstanceUID'])['series_size_MB'].transform('sum')
        patient_study_df['patient_study_series_count'] = patient_study_df.groupby(['PatientID', 'StudyInstanceUID'])['SeriesInstanceUID'].transform('count')
        patient_study_df['patient_study_instance_count'] = patient_study_df.groupby(['PatientID', 'StudyInstanceUID'])['instanceCount'].transform('count')

        patient_study_df = patient_study_df.rename(columns={'collection_id': 'Collection', 'patient_study_series_count': 'SeriesCount'})

        #patient_study_df = patient_study_df[['PatientID', 'PatientSex', 'Collection', 'PatientAge', 'StudyInstanceUID', 'StudyDate', 'StudyDescription', 'patient_study_size_MB', 'SeriesCount', 'patient_study_instance_count']]
        patient_study_df = patient_study_df[['StudyInstanceUID', 'StudyDate', 'StudyDescription', 'SeriesCount']]
        # Group by 'StudyInstanceUID' to make sure there is only one studyid in the GUI
        patient_study_df = patient_study_df.groupby('StudyInstanceUID').agg({
            'StudyDate': lambda x: ','.join(x[x != ''].unique()),
            'StudyDescription': lambda x: ','.join(x[x != ''].unique()),
            'SeriesCount': lambda x: int(x[x != ''].iloc[0]) if len(x[x != '']) > 0 else 0
        }).reset_index()

        patient_study_df = patient_study_df.drop_duplicates().sort_values(by=['StudyDate','StudyDescription','SeriesCount'])



        # Convert DataFrame to a list of dictionaries for the API-like response
        idc_response = patient_study_df.to_dict(orient="records")

        logging.debug("Get patient study response: %s", str(idc_response))

        return idc_response


    def get_series(self, collection=None, patientId=None, studyInstanceUID=None, modality=None, outputFormat="json"):
        if collection is not None:
            patient_series_df = self.index[self.index['collection_id'] == collection].copy()  # Make a copy
        elif patientId is not None:
            patient_series_df = self.index[self.index['PatientID'] == patientId].copy()  # Make a copy
        elif studyInstanceUID is not None:
            patient_series_df = self.index[self.index['StudyInstanceUID'] == studyInstanceUID].copy()  # Make a copy
        elif modality is not None:
            patient_series_df = self.index[self.index['Modality'] == modality].copy()  # Make a copy
        else:
            patient_series_df = self.index.copy()  # Make a copy

        patient_series_df = patient_series_df.rename(columns={'collection_id': 'Collection', 'instanceCount': 'instance_count'})
        patient_series_df['ImageCount']=1
        patient_series_df = patient_series_df[['StudyInstanceUID', 'SeriesInstanceUID', 'Modality', 'SeriesDate', 'Collection', 'BodyPartExamined', 'SeriesDescription', 'Manufacturer', 'ManufacturerModelName', 'series_size_MB','SeriesNumber', 'instance_count', 'ImageCount']]

        patient_series_df = patient_series_df.drop_duplicates().sort_values(by=['Modality','SeriesDate','SeriesDescription','BodyPartExamined', 'SeriesNumber'])
        # Convert DataFrame to a list of dictionaries for the API-like response
        idc_response = patient_series_df.to_dict(orient="records")

        logging.debug("Get series response: %s", str(idc_response))

        return idc_response



    def get_image(self, seriesInstanceUid, downloadDir, download=True):
        series_url = self.index[self.index['SeriesInstanceUID']==seriesInstanceUid]['series_aws_location'].iloc[0]
        #series_url = f"s3://{row['aws_bucket']}/{row['crdc_series_uuid']}/*"
        print(series_url)
        import subprocess

        cmd = [self.s5cmdPath, '--no-sign-request', '--endpoint-url', 'https://s3.amazonaws.com', 'cp',
                series_url, downloadDir]
        #logging.debug(" ".join(cmd))

        if download:
            ret = subprocess.run(cmd)

        return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    client = IDCClient()
    # r = client.get_image('1.3.6.1.4.1.14519.5.2.1.6834.5010.130448511786154037246331774347', '.', download=False)
    # r = client.get_patient(collection='4d_lung', outputFormat="json")
    # r = client.get_patient_study( collection='4d_lung', patientId='108_HM10395', studyInstanceUid='1.3.6.1.4.1.14519.5.2.1.6834.5010.185173640297170335553556115001', outputFormat="json")
    # r = client.get_series(collection='4d_lung', patientId='108_HM10395', studyInstanceUID='1.3.6.1.4.1.14519.5.2.1.6834.5010.185173640297170335553556115001', modality=None, outputFormat="json")
