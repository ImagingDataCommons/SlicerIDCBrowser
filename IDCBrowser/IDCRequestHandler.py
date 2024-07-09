# slicer_server_utils.py

import os
import subprocess
import time
import logging
import requests
from slicer.util import VTKObservationMixin
import qt
import slicer
import ctk
# IDCRequestHandler.py

from WebServerLib.BaseRequestHandler import BaseRequestHandler, BaseRequestLoggingFunction
import urllib
import os
from typing import Optional
from idc_index import index

# PORT = 2042

# def get_slicer_location():
#     launcherPath = qt.QDir.toNativeSeparators(
#         qt.QFileInfo(slicer.app.launcherExecutableFilePath).absoluteFilePath()
#     )
#     return launcherPath

# def is_server_running():
#     try:
#         response = requests.get(f"http://127.0.0.1:{PORT}/idc/collections", timeout=3)
#         if 'applicationName' in response.json():
#             return True
#     except Exception as e:
#         logging.debug("Application is not available: " + str(e))
#     return False

# def start_server(slicer_executable=None, timeoutSec=60):
#     # if not slicer_executable:
#     #     if 'SLICER_EXECUTABLE' not in os.environ:
#     #         os.environ['SLICER_EXECUTABLE'] = get_slicer_location()
#     #         slicer_executable = get_slicer_location()
#     # p = subprocess.Popen([slicer_executable, "--python-code", f"wslogic = getModuleLogic('WebServer'); wslogic.port={PORT}; wslogic.enableSlicer=False; wslogic.enableStaticPages=False; wslogic.enableDICOM=True; wslogic.requestHandlers = [IDCRequestHandler()], wslogic.start()"])
#     # start = time.time()
#     # connected = False
#     # while not connected:
#     #     connected = is_server_running()
#     #     if time.time() - start > timeoutSec:
#     #         raise requests.exceptions.ConnectTimeout("Timeout while waiting for application to start")
#     # return p
#     if not is_server_running():
        
# The following part remains unchanged
#         PORT = 2042
#         import WebServer

#         try:
#             logic.stop()
#         except NameError:
#             pass

#         logMessage = WebServer.WebServerLogic.defaultLogMessage
#         requestHandlers = [IDCRequestHandler()]
#         logic = WebServer.WebServerLogic(port=PORT, logMessage=logMessage, enableSlicer=True, enableStaticPages=False, enableDICOM=False, requestHandlers=requestHandlers)

#         logic.start()

import os
import subprocess
import time
import logging
import requests
from slicer.util import VTKObservationMixin
import qt
import slicer
import ctk
# IDCRequestHandler.py

from WebServerLib.BaseRequestHandler import BaseRequestHandler, BaseRequestLoggingFunction
import urllib
import os
from typing import Optional
from idc_index import index

class IDCRequestHandler(BaseRequestHandler):

    def __init__(self, logMessage: Optional[BaseRequestLoggingFunction] = None):
        self.logMessage = logMessage
        self.client = index.IDCClient()
        self.index_df = self.client.index

        # if not is_server_running():
        #     start_server()

    def canHandleRequest(self, uri: bytes, **_kwargs) -> float:
        parsedURL = urllib.parse.urlparse(uri)
        if parsedURL.path.startswith(b"/idc"):
            return 0.5
        return 0.0

    def handleRequest(self, method: str, uri: bytes, requestBody: bytes, **_kwargs) -> tuple[bytes, bytes]:
        parsedURL = urllib.parse.urlparse(uri)
        splitPath = parsedURL.path.split(b"/")

        if len(splitPath) > 2:
            if splitPath[2] == b"collections":
                return self.handleCollections()
            elif splitPath[2] == b"download" and splitPath[3] == b"seriesInstanceUID":
                series_uids = splitPath[4].decode().split(",")
                return self.handleDownload(series_uids)
            elif splitPath[2] == b"download" and splitPath[3] == b"studyInstanceUID":
                study_uids = splitPath[4].decode().split(",")
                filtered_df = self.index_df[self.index_df['StudyInstanceUID'].isin(study_uids)]
                series_uids_from_study_uid = filtered_df['SeriesInstanceUID'].tolist()
                return self.handleDownload(series_uids_from_study_uid)
            else:
                return b"text/plain", b"Unhandled IDC request path"
        else:
            return b"text/plain", b"Invalid IDC request path"

    def handleCollections(self) -> tuple[bytes, bytes]:
        try:
            collections = self.client.get_collections()
            responseBody = f"Available collections: {', '.join(collections)}".encode()
            contentType = b"text/plain"
        except Exception as e:
            responseBody = f"Error fetching collections: {e}".encode()
            contentType = b"text/plain"
            if self.logMessage:
                self.logMessage(responseBody.decode())

        return contentType, responseBody

    def handleDownload(self, uids: list[str]) -> tuple[bytes, bytes]:
        destFolderPath = slicer.mrmlScene.GetCacheManager().GetRemoteCacheDirectory()

        try:
            self.client.download_from_selection(seriesInstanceUID=uids, downloadDir=destFolderPath, dirTemplate="%SeriesInstanceUID")
            indexer = ctk.ctkDICOMIndexer()
            for uid in uids:
                download_folder_path = os.path.join(destFolderPath, uid)
                indexer.addDirectory(slicer.dicomDatabase, download_folder_path)
                plugin = slicer.modules.dicomPlugins["DICOMScalarVolumePlugin"]()
                dicomDatabase = slicer.dicomDatabase
                fileList = dicomDatabase.filesForSeries(uid.replace("'", ""))
                loadables = plugin.examine([fileList])
                if len(loadables) > 0:
                    volume = plugin.load(loadables[0])
                    logging.debug("Loaded volume: " + volume.GetName())
                else:
                    raise Exception("Unable to load DICOM content. Please retry from DICOM Browser!")

                responseBody = f"Downloaded and indexed UID(s): {', '.join(uids)}".encode()
                contentType = b"text/plain"
        except Exception as e:
            responseBody = f"Error downloading or indexing UID(s): {e}".encode()
            contentType = b"text/plain"
            if self.logMessage:
                self.logMessage(responseBody.decode())

        return contentType, responseBody


# The following part remains unchanged
PORT = 2042
import WebServer

try:
    logic.stop()
except NameError:
    pass

logMessage = WebServer.WebServerLogic.defaultLogMessage
requestHandlers = [IDCRequestHandler()]
logic = WebServer.WebServerLogic(port=PORT, logMessage=logMessage, enableSlicer=True, enableStaticPages=False, enableDICOM=True, requestHandlers=requestHandlers)

logic.start()