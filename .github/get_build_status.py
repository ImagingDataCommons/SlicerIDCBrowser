import requests
import pandas as pd
import sys
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
slicerExtensionName ='ImageMaker'
# API URL
api_url = f"https://slicer.cdash.org/api/v1/index.php?project=SlicerPreview&filtercount=1&showfilters=1&field1=buildname&compare1=63&value1={slicerExtensionName}"

# Make the API request and store the JSON response
response = requests.get(api_url)

if response.status_code == 200:
    # Parse the JSON response
    api_result = response.json()

    # Extract the necessary information from the API result
    api_call_time = api_result["datetime"]
    builds = api_result["buildgroups"][0]["builds"]

    # Create a list of dictionaries with the desired data
    data = []
    for build in builds:
        build_data = {
            "APICallTime": api_call_time,
            "BuildTriggerTime": build["builddate"],
            "BuildName": build["buildname"],
            "BuildPlatform": build.get("buildplatform", None),
            "ConfigureErrors": build.get("configure", {}).get("error", 0),
            "ConfigureWarnings": build.get("configure", {}).get("warning", 0),
            "HasCompilationData": build.get("hascompilation", False),
            "CompilationErrors": build.get("compilation", {}).get("error", 0),
            "CompilationWarnings": build.get("compilation", {}).get("warning", 0),
            "HasTestData": build.get("hastest", False),
            "TestNotRun": build.get("test", {}).get("notrun", 0),
            "TestFail": build.get("test", {}).get("fail", 0),
            "TestPass": build.get("test", {}).get("pass", 0),
        }
        data.append(build_data)

    # Create a DataFrame
    df = pd.DataFrame(data)
    print(df)
    error_sum = df['ConfigureErrors'].sum()+ df['CompilationErrors'].sum()+df['TestFail'].sum()
    has_errors = error_sum > 0
    if has_errors:
      sys.exit(1)
    else:
      sys.exit(0)
else:
    print(f"Failed to retrieve data. Status code: {response.status_code}")
