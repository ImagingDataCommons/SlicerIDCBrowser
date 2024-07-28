import os
import slicer
import urllib.parse
from slicer.ScriptedLoadableModule import *
from WebServer import WebServerLogic
from typing import Optional
from WebServerLib.BaseRequestHandler import (
    BaseRequestHandler,
    BaseRequestLoggingFunction,
)

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
import sys
import shlex


class IDCRequestHandler(BaseRequestHandler):

    def __init__(self, logMessage: Optional[BaseRequestLoggingFunction] = None):
        self.logMessage = logMessage
        self.client = index.IDCClient()
        self.index_df = self.client.index

    def canHandleRequest(self, uri: bytes, **_kwargs) -> float:
        parsedURL = urllib.parse.urlparse(uri)
        if parsedURL.path.startswith(b"/idc"):
            return 0.5
        return 0.0

    def handleRequest(
        self, method: str, uri: bytes, requestBody: bytes, **_kwargs
    ) -> tuple[bytes, bytes]:
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
                filtered_df = self.index_df[
                    self.index_df["StudyInstanceUID"].isin(study_uids)
                ]
                series_uids_from_study_uid = filtered_df["SeriesInstanceUID"].tolist()
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
            self.client.download_from_selection(
                seriesInstanceUID=uids,
                downloadDir=destFolderPath,
                dirTemplate="%SeriesInstanceUID",
                use_s5cmd_sync=True,
            )
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
                    raise Exception(
                        "Unable to load DICOM content. Please retry from DICOM Browser!"
                    )
                responseBody = (
                    f"Downloaded and indexed UID(s): {', '.join(uids)}".encode()
                )
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
        self.parent.contributors = [
            "Vamsi Thiriveedhi(ImagingDataCommons), Steve Pieper (Isomics, Inc.)"
        ]
        self.parent.helpText = """This module registers an IDCRequestHandler to handle IDC-related requests."""
        self.parent.acknowledgementText = """This was a project born during PW 40 when @pieper once mentioned the idea of using Slicer just the way we use zoom. 
This post (https://discourse.slicer.org/t/how-to-load-nifti-file-from-web-browser-link/18664/5) showed that it was indeed possible, and the current implementation
is inspired from it, and the slicerio package, which was originally developed by @lassoan and team. 
see https://github.com/ImagingDataCommons/SlicerIDCBrowser/pull/43 for more info.
"""

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
        logic = WebServerLogic(
            port=PORT,
            logMessage=logMessage,
            enableSlicer=True,
            enableStaticPages=False,
            enableDICOM=True,
            requestHandlers=requestHandlers,
        )

        logic.start()
        print("IDC Request Handler has been registered and server started.")

        self.writeResolverScript()
        self.registerCustomProtocol()

    def writeResolverScript(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        resolver_script_path = os.path.join(current_dir, "Resources", "resolver.py")

        resolver_script_content = """import sys
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
"""

        with open(resolver_script_path, "w") as f:
            f.write(resolver_script_content)
        print(f"Resolver script written to {resolver_script_path}")

    def registerCustomProtocol(self):
        if platform.system() == "Linux":
            # Check if the protocol is already registered

            if os.path.exists(
                os.path.expanduser("~/.local/share/applications/idcbrowser.desktop")
            ):
                print("IDC Browser URL protocol is already registered.")
                return
            # Get the current directory

            current_dir = os.path.dirname(os.path.realpath(__file__))
            python_script_path = shlex.quote(
                os.path.join(current_dir, "Resources", "resolver.py")
            )

            python_dir = slicer.app.slicerHome
            normalized_python_dir = os.path.normpath(python_dir)

            # Construct the path to PythonSlicer.exe in the same directory

            python_path = shlex.quote(
                os.path.join(normalized_python_dir, "bin", "PythonSlicer")
            )
            # Register IDC Browser URL protocol

            with open(
                os.path.expanduser("~/.local/share/applications/idcbrowser.desktop"),
                "w",
            ) as f:
                f.write(
                    f"""[Desktop Entry]
Name=IDC Browser
Exec={python_path} {python_script_path} %u
Type=Application
Terminal=false
MimeType=x-scheme-handler/idcbrowser;
"""
                )
            # Update MIME database

            os.system("update-desktop-database ~/.local/share/applications/")
            os.system("xdg-mime default idcbrowser.desktop x-scheme-handler/idcbrowser")
        elif platform.system() == "Windows":

            # Get the directory of the current Python executable

            python_dir = os.path.dirname(sys.executable)

            # Construct the path to PythonSlicer.exe in the same directory

            python_path = os.path.join(python_dir, "PythonSlicer.exe")

            current_dir = os.path.dirname(os.path.realpath(__file__))
            python_script_path = os.path.join(current_dir, "Resources", "resolver.py")

            # Register IDC Browser URL protocol in Windows Registry

            import winreg as reg

            try:
                reg.CreateKey(reg.HKEY_CURRENT_USER, r"Software\Classes\idcbrowser")
                with reg.OpenKey(
                    reg.HKEY_CURRENT_USER,
                    r"Software\Classes\idcbrowser",
                    0,
                    reg.KEY_WRITE,
                ) as key:
                    reg.SetValue(key, None, reg.REG_SZ, "URL:IDC Browser Protocol")
                    reg.SetValueEx(key, "URL Protocol", 0, reg.REG_SZ, "")
                reg.CreateKey(
                    reg.HKEY_CURRENT_USER,
                    r"Software\Classes\idcbrowser\shell\open\command",
                )
                with reg.OpenKey(
                    reg.HKEY_CURRENT_USER,
                    r"Software\Classes\idcbrowser\shell\open\command",
                    0,
                    reg.KEY_WRITE,
                ) as key:
                    reg.SetValue(
                        key,
                        None,
                        reg.REG_SZ,
                        f'"{python_path}" "{python_script_path}" "%1"',
                    )
                print("IDC Browser URL protocol has been registered on Windows.")
            except Exception as e:
                print(f"Failed to register IDC Browser URL protocol on Windows: {e}")
        elif platform.system() == "Darwin":
            slicer_exec_dir = os.path.dirname(sys.executable)
            parent_dir = os.path.dirname(slicer_exec_dir)

            # Now, you can construct the path to PythonSlicer

            python_path = shlex.quote(os.path.join(parent_dir, "bin", "PythonSlicer"))

            current_dir = os.path.dirname(os.path.realpath(__file__))
            python_script_path = shlex.quote(
                os.path.join(current_dir, "Resources", "resolver.py")
            )

            def check_macos_slicer_protocol_registration():
                plist_path = os.path.expanduser(
                    "/Applications/slicer-app.app/Contents/Info.plist"
                )
                return os.path.exists(plist_path)

            if check_macos_slicer_protocol_registration():
                print("Slicer URL protocol is already registered.")
                return
            # Create the AppleScript

            applescript_path = os.path.expanduser("~/slicer.applescript")
            with open(applescript_path, "w") as applescript_file:
                applescript_file.write(
                    f"""
            on open location this_URL
                do shell script "{python_path} {python_script_path} " & quoted form of this_URL
            end open location
            """
                )
            # Compile the AppleScript into an app

            os.system(f"osacompile -o /Applications/slicer-app.app {applescript_path}")

            # Create or modify the plist file

            plist_content = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>CFBundleAllowMixedLocalizations</key>
            <true/>
            <key>CFBundleDevelopmentRegion</key>
            <string>en</string>
            <key>CFBundleExecutable</key>
            <string>applet</string>
            <key>CFBundleIconFile</key>
            <string>applet</string>
            <key>CFBundleInfoDictionaryVersion</key>
            <string>6.0</string>
            <key>CFBundleName</key>
            <string>slicer-app</string>
            <key>CFBundlePackageType</key>
            <string>APPL</string>
            <key>CFBundleSignature</key>
            <string>aplt</string>
            <key>LSMinimumSystemVersionByArchitecture</key>
            <dict>
                <key>x86_64</key>
                <string>10.6</string>
            </dict>
            <key>LSRequiresCarbon</key>
            <true/>
            <key>NSAppleEventsUsageDescription</key>
            <string>This script needs to control other applications to run.</string>
            <key>NSAppleMusicUsageDescription</key>
            <string>This script needs access to your music to run.</string>
            <key>NSCalendarsUsageDescription</key>
            <string>This script needs access to your calendars to run.</string>
            <key>NSCameraUsageDescription</key>
            <string>This script needs access to your camera to run.</string>
            <key>NSContactsUsageDescription</key>
            <string>This script needs access to your contacts to run.</string>
            <key>NSHomeKitUsageDescription</key>
            <string>This script needs access to your HomeKit Home to run.</string>
            <key>NSMicrophoneUsageDescription</key>
            <string>This script needs access to your microphone to run.</string>
            <key>NSPhotoLibraryUsageDescription</key>
            <string>This script needs access to your photos to run.</string>
            <key>NSRemindersUsageDescription</key>
            <string>This script needs access to your reminders to run.</string>
            <key>NSSiriUsageDescription</key>
            <string>This script needs access to Siri to run.</string>
            <key>NSSystemAdministrationUsageDescription</key>
            <string>This script needs access to administer this system to run.</string>
            <key>OSAAppletShowStartupScreen</key>
            <false/>
            <key>CFBundleIdentifier</key>
            <string>slicer.protocol.registration</string>
            <key>CFBundleURLTypes</key>
            <array>
                <dict>
                    <key>CFBundleURLName</key>
                    <string>idcbrowser</string>
                    <key>CFBundleURLSchemes</key>
                    <array>
                        <string>idcbrowser</string>
                    </array>
                </dict>
            </array>
        </dict>
        </plist>
        """

            plist_path = os.path.expanduser(
                "/Applications/slicer-app.app/Contents/Info.plist"
            )
            with open(plist_path, "w") as plist_file:
                plist_file.write(plist_content)
            print("Slicer URL protocol registered successfully.")
        else:
            print(
                "IDC Browser URL protocol registration is not supported on this operating system."
            )
