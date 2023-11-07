SELECT
string_agg(distinct PatientID) PatientID,
string_agg(distinct PatientAge) PatientAge,
string_agg(distinct PatientSex) PatientSex,
string_agg(distinct collection_id) collection_id,
string_agg(distinct source_DOI)  as DOI,
string_agg(distinct StudyInstanceUID) StudyInstanceUID,
string_agg(distinct cast(StudyDate as STRING)) StudyDate,
string_agg(distinct StudyDescription) StudyDescription,
string_agg(distinct Modality) Modality,
string_agg(distinct Manufacturer) Manufacturer,
string_agg(distinct ManufacturerModelName) ManufacturerModelName,
SeriesInstanceUID,
string_agg(distinct cast(SeriesDate as STRING)) SeriesDate,
string_agg(distinct SeriesDescription)  SeriesDescription,
string_agg(distinct BodyPartExamined) BodyPartExamined,
string_agg(distinct SeriesNumber) SeriesNumber,
ANY_VALUE(CONCAT("s3://", SPLIT(aws_url,"/")[SAFE_OFFSET(2)], "/", crdc_series_uuid, "/*")) as series_aws_location,
COUNT(SOPInstanceUID) as instanceCount,
ROUND(SUM(instance_size)/(1000*1000), 2) as series_size_MB,
FROM
  `bigquery-public-data.idc_v15.dicom_all`

GROUP BY
SeriesInstanceUID
