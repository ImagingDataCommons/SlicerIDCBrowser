import os
import re
import urllib
import requests
from google.cloud import bigquery

# Set up BigQuery client
project_id='idc-external-025'
client = bigquery.Client(project=project_id)

# Get current index version
url='https://raw.githubusercontent.com/vkt1414/SlicerIDCBrowser/csv_index/IDCBrowser/Resources/csv_index.sql'
current_index_version = re.search(r'idc_v(\d+)', urllib.request.urlopen(url).read().decode('utf-8')).group(1)
print('idc_version_in_index: '+current_index_version +'\n')

# Get latest IDC release version
view_id = "bigquery-public-data.idc_current.dicom_all_view"
view = client.get_table(view_id)
latest_idc_release_version= re.search(r'idc_v(\d+)', view.view_query).group(1)
print('latest_idc_release_version: '+latest_idc_release_version +'\n')

# Check if current index version is outdated
if current_index_version < latest_idc_release_version:
  # Update SQL query
  modified_sql_query = re.sub(r'idc_v(\d+)', 'idc_v'+latest_idc_release_version, urllib.request.urlopen(url).read().decode('utf-8'))
  print('modified_sql_query:\n'+modified_sql_query)
  # Save the modified SQL query as a SQL file
  with open('csv_index.sql', 'w') as file:
    file.write(modified_sql_query)
  
  # Execute SQL query and save result as CSV
  df = client.query(modified_sql_query).to_dataframe()
  csv_file_name = 'csv_index_'+'idc_v'+latest_idc_release_version+'.csv'
  df.to_csv(csv_file_name, escapechar='\\')

  # Set up GitHub API request headers
  headers = {
    'Accept': 'application/vnd.github+json',
    'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
    'X-GitHub-Api-Version': '2022-11-28'
  }

  # Create a new release
  data = {
    'tag_name': 'v' + latest_idc_release_version,
    'target_commitish': 'main',
    'name': 'v' + latest_idc_release_version,
    'body': 'Found newer IDC release with version '+latest_idc_release_version+ '. So updating the index also from idc_v'+current_index_version+' to idc_v'+latest_idc_release_version,
    'draft': False,
    'prerelease': False,
    'generate_release_notes': False
  }
  response = requests.post('https://api.github.com/repos/OWNER/REPO/releases', headers=headers, json=data)

  # Check if release was created successfully
  if response.status_code == 201:
    # Get upload URL for release assets
    upload_url = response.json()['upload_url']
    upload_url = upload_url[:upload_url.find('{')]
    upload_url += '?name=' + csv_file_name

    # Upload CSV file as release asset
    headers['Content-Type'] = 'application/octet-stream'
    with open(csv_file_name, 'rb') as data:
      response = requests.post(upload_url, headers=headers, data=data)

      # Check if asset was uploaded successfully
      if response.status_code != 201:
        print('Error uploading asset: ' + response.text)
  else:
    print('Error creating release: ' + response.text)
