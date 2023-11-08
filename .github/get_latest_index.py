import re, urllib
from google.cloud import bigquery


project_id='idc-external-025'
client = bigquery.Client(project=project_id)

url='https://raw.githubusercontent.com/vkt1414/SlicerIDCBrowser/csv_index/IDCBrowser/Resources/csv_index.sql'

current_index_version = re.search(r'idc_v(\d+)', urllib.request.urlopen(url).read().decode('utf-8')).group(1)

view_id = "bigquery-public-data.idc_current.dicom_all_view"

view = client.get_table(view_id)

latest_idc_release_version= re.search(r'idc_v(\d+)', view.view_query).group(1)

if current_index_version < latest_idc_release_version:
  modified_sql_query = re.sub(r'idc_v(\d+)', 'idc_v'+latest_idc_release_version, urllib.request.urlopen(url).read().decode('utf-8'))
  
  # Save the modified SQL query as a SQL file
  with open('csv_index.sql', 'w') as file:
    file.write(modified_sql_query)
  
  bigquery_sql = f"""{modified_sql_query}"""

  df = client.query(bigquery_sql).to_dataframe()

  csv_file_name = 'csv_index_'+'idc_v'+latest_idc_release_version+'.csv'

  df.to_csv(csv_file_name, escapechar='\\')