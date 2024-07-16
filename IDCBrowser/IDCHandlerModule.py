import os
import slicer
import urllib.parse
from slicer.ScriptedLoadableModule import *
from WebServer import WebServerLogic
from typing import Optional
from WebServerLib.BaseRequestHandler import BaseRequestHandler, BaseRequestLoggingFunction

import os
import platform
import subprocess
import time
import logging
import requests
from slicer.util import VTKObservationMixin
import qt
import slicer
import ctk
from idc_index import index

class IDCRequestHandler(BaseRequestHandler):

    def __init__(self, logMessage: Optional[BaseRequestLoggingFunction] = None):
        self.logMessage = logMessage
        self.client = index.IDCClient()
        self.index_df = self.client.index

    def canHandleRequest(self, uri: bytes, **_kwargs) -> float:
        parsedURL = urllib.parse.urlparse(uri)
        if (parsedURL.path.startswith(b"/idc")):
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


class IDCHandlerModule(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "IDC Handler Module"
        self.parent.categories = ["Examples"]
        self.parent.contributors = ["Your Name (Your Organization)"]
        self.parent.helpText = """This module registers an IDCRequestHandler to handle IDC-related requests."""
        self.parent.acknowledgementText = """This module was developed by Your Name, Your Organization."""

        slicer.app.connect("startupCompleted()", self.onStartupCompleted)

    def onStartupCompleted(self):
        print("SlicerStartupCompleted emitted")

        PORT = 2042
        try:
            logic.stop()
        except NameError:
            pass

        logMessage = WebServerLogic.defaultLogMessage
        requestHandlers = [IDCRequestHandler()]
        logic = WebServerLogic(port=PORT, logMessage=logMessage, enableSlicer=True, enableStaticPages=False, enableDICOM=True, requestHandlers=requestHandlers)

        logic.start()
        print("IDC Request Handler has been registered and server started.")
        
        self.writeResolverScript()
        self.registerCustomProtocol()

    def writeResolverScript(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        resolver_script_path = os.path.join(current_dir,'Resources', 'resolver.py')

        resolver_script_content = '''import sys
import urllib.parse
import requests
import webbrowser

def resolve_url(url):
    # Parse the URL
    parsed_url = urllib.parse.urlparse(url)

    # Remove the scheme (idcbrowser://) from the URL and split the path
    path_parts = parsed_url.netloc.split('/') + parsed_url.path.split('/')[1:]

    # Check the first part of the path to determine the endpoint
    if path_parts[0] == 'collections':
        new_url = "http://localhost:2042/idc/collections"
       # Open the new URL in a web browser
        webbrowser.open(new_url)
    elif path_parts[0] == 'series':
        new_url = f"http://localhost:2042/idc/download/seriesInstanceUID/{path_parts[1]}"
    elif path_parts[0] == 'studies':
        new_url = f"http://localhost:2042/idc/download/studyInstanceUID/{path_parts[1]}"
    else:
        print(f"Unhandled path: {path_parts[0]}")
        return

    # Make the request to the new URL
    response = requests.get(new_url)

    # Print the response
    print(response.text)

if __name__ == "__main__":
    # The URL is passed as the first argument
    url = sys.argv[1]

    # Resolve the URL
    resolve_url(url)
'''

        with open(resolver_script_path, 'w') as f:
            f.write(resolver_script_content)
        print(f"Resolver script written to {resolver_script_path}")

    def registerCustomProtocol(self):
        if platform.system() == "Linux":
            # Check if the protocol is already registered
            if os.path.exists(os.path.expanduser("~/.local/share/applications/idcbrowser.desktop")):
                print("IDC Browser URL protocol is already registered.")
                return

            # Get the current directory
            current_dir = os.path.dirname(os.path.realpath(__file__))
            python_script_path = os.path.join(current_dir, 'resolver.py')

            # Register IDC Browser URL protocol
            with open(os.path.expanduser("~/.local/share/applications/idcbrowser.desktop"), "w") as f:
                f.write(f"""[Desktop Entry]
Name=IDC Browser
Exec=python3 {python_script_path} %u
Type=Application
Terminal=false
MimeType=x-scheme-handler/idcbrowser;
""")

            # Update MIME database
            os.system("update-desktop-database ~/.local/share/applications/")
            os.system("xdg-mime default idcbrowser.desktop x-scheme-handler/idcbrowser")
        
        elif platform.system() == "Windows":
            
            # Get the directory of the current Python executable
            python_dir = os.path.dirname(sys.executable)

            # Construct the path to PythonSlicer.exe in the same directory
            python_path = os.path.join(python_dir, "PythonSlicer.exe")

            current_dir = os.path.dirname(os.path.realpath(__file__))
            python_script_path = os.path.join(current_dir,'Resources', 'resolver.py')

            # Register IDC Browser URL protocol in Windows Registry
            import winreg as reg

            try:
                reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\idcbrowser")
                with reg.OpenKey(reg.HKEY_CURRENT_USER, r"Software\Classes\idcbrowser", 0, reg.KEY_WRITE) as key:
                    reg.SetValue(key, None, reg.REG_SZ, "URL:IDC Browser Protocol")
                    reg.SetValueEx(key, "URL Protocol", 0, reg.REG_SZ, "")
                    
                reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\idcbrowser\shell\open\command")
                with reg.OpenKey(reg.HKEY_CURRENT_USER, r"Software\Classes\idcbrowser\shell\open\command", 0, reg.KEY_WRITE) as key:
                    reg.SetValue(key, None, reg.REG_SZ, f'"{python_path}" "{python_script_path}" "%1"')
                    
                print("IDC Browser URL protocol has been registered on Windows.")
            except Exception as e:
                print(f"Failed to register IDC Browser URL protocol on Windows: {e}")    
        else:
            print("IDC Browser URL protocol registration is not supported on this operating system.")

