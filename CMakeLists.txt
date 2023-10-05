cmake_minimum_required(VERSION 2.8.9)

project(TCIABrowser)

#-----------------------------------------------------------------------------
set(EXTENSION_HOMEPAGE "https://github.com/ImagingDataCommons/SlicerIDCBrowser")
set(EXTENSION_CATEGORY "Informatics")
set(EXTENSION_CONTRIBUTORS "Andrey Fedorov (SPL and BWH)")
set(EXTENSION_DESCRIPTION "A Module to explore and access imaging data available from National Cancer Institute Imaging Data Commons.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/ImagingDataCommons/SlicerIDCBrowser/main/IDCBrowser/Resources/Icons/IDCBrowser.png")
set(EXTENSION_SCREENSHOTURLS "https://github.com/ImagingDataCommons/SlicerIDCBrowser/blob/main/IDCBrowser/Resources/Screenshot/screenshot.png?raw=true")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
add_subdirectory(TCIABrowser)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_CPACK})
