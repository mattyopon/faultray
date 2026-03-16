# FaultRay Backtest Accuracy Report

Generated: 2026-03-16 17:11:27
Total Incidents: 18

## Overall Accuracy Summary

| Metric | Value |
|--------|-------|
| Avg Precision | 1.000 |
| Avg Recall | 0.499 |
| Avg F1 Score | 0.626 |
| Avg Severity Accuracy | 0.517 |
| Avg Downtime MAE (min) | 3156.72 |
| Avg Confidence | 0.479 |

## Per-Incident Results

| Incident ID | Component | Precision | Recall | F1 | Sev Acc | DT MAE | Confidence |
|-------------|-----------|-----------|--------|----|---------|--------|------------|
| aws-us-east-1-2021-12 | app_server | 1.000 | 0.143 | 0.250 | 0.210 | 655.0 | 0.188 |
| aws-s3-2017-02 | s3_storage | 1.000 | 0.750 | 0.857 | 0.700 | 299.5 | 0.639 |
| meta-bgp-2021-10 | dns_resolver | 1.000 | 0.500 | 0.667 | 0.340 | 355.0 | 0.435 |
| cloudflare-2022-06 | cdn | 1.000 | 0.667 | 0.800 | 0.970 | 119.5 | 0.691 |
| gcp-2019-06 | gce_instance | 1.000 | 0.333 | 0.500 | 0.340 | 260.0 | 0.352 |
| azure-2023-01 | azure_vm | 1.000 | 0.500 | 0.667 | 0.500 | 539.5 | 0.483 |
| github-ddos-2018 | cdn | 1.000 | 0.333 | 0.500 | 0.740 | 15.0 | 0.622 |
| fastly-2021-06 | cdn | 1.000 | 1.000 | 1.000 | 0.900 | 48.5 | 0.808 |
| crowdstrike-2024-07 | app_server | 1.000 | 0.333 | 0.500 | 0.340 | 1435.0 | 0.352 |
| aws-dynamodb-2015-09 | dynamo_db | 1.000 | 1.000 | 1.000 | 0.700 | 299.5 | 0.710 |
| gcp-lb-2021-11 | main_lb | 1.000 | 0.500 | 0.667 | 0.740 | 145.0 | 0.555 |
| dyn-ddos-2016-10 | dns_resolver | 1.000 | 1.000 | 1.000 | 0.340 | 475.0 | 0.602 |
| aws-kinesis-2020-11 | lambda_fn | 1.000 | 0.250 | 0.400 | 0.300 | 595.0 | 0.290 |
| slack-2022-02 | primary_db | 1.000 | 0.500 | 0.667 | 0.900 | 299.5 | 0.603 |
| aws-ebs-2011-04 | app_server | 1.000 | 0.333 | 0.500 | 0.340 | 2875.0 | 0.352 |
| roblox-2021-10 | app_server | 1.000 | 0.250 | 0.400 | 0.300 | 4375.0 | 0.290 |
| azure-ad-2021-03 | azure_vm | 1.000 | 0.250 | 0.400 | 0.300 | 835.0 | 0.290 |
| ovh-fire-2021-03 | app_server | 1.000 | 0.333 | 0.500 | 0.340 | 43195.0 | 0.352 |

## Calibration Recommendations

- **downtime_bias_correction**: 3156.72
- **dependency_weight_threshold_reduction**: 0.1
- **severity_bias_correction**: 4.47

## Detailed Results

### aws-us-east-1-2021-12

- **Failed Component**: app_server
- **Actual Affected**: app_server, primary_db, redis, lambda_fn, message_queue, monitoring, container_service
- **Predicted Affected**: app_server
- **Actual Severity**: critical
- **Predicted Severity**: 1.1
- **Actual Downtime**: 660 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.143 | **F1**: 0.250
- **True Positives**: app_server
- **False Negatives**: container_service, lambda_fn, message_queue, monitoring, primary_db, redis

### aws-s3-2017-02

- **Failed Component**: s3_storage
- **Actual Affected**: s3_storage, app_server, lambda_fn, message_queue
- **Predicted Affected**: app_server, lambda_fn, s3_storage
- **Actual Severity**: critical
- **Predicted Severity**: 6.0
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 0.750 | **F1**: 0.857
- **True Positives**: app_server, lambda_fn, s3_storage
- **False Negatives**: message_queue

### meta-bgp-2021-10

- **Failed Component**: dns_resolver
- **Actual Affected**: dns_resolver, cdn
- **Predicted Affected**: dns_resolver
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 360 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.500 | **F1**: 0.667
- **True Positives**: dns_resolver
- **False Negatives**: cdn

### cloudflare-2022-06

- **Failed Component**: cdn
- **Actual Affected**: cdn, dns_resolver, api_gw
- **Predicted Affected**: cdn, dns_resolver
- **Actual Severity**: major
- **Predicted Severity**: 5.3
- **Actual Downtime**: 120 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 0.667 | **F1**: 0.800
- **True Positives**: cdn, dns_resolver
- **False Negatives**: api_gw

### gcp-2019-06

- **Failed Component**: gce_instance
- **Actual Affected**: gce_instance, cloud_sql, gcs_storage
- **Predicted Affected**: gce_instance
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 265 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.333 | **F1**: 0.500
- **True Positives**: gce_instance
- **False Negatives**: cloud_sql, gcs_storage

### azure-2023-01

- **Failed Component**: azure_vm
- **Actual Affected**: azure_vm, azure_sql, azure_blob, azure_lb
- **Predicted Affected**: azure_lb, azure_vm
- **Actual Severity**: critical
- **Predicted Severity**: 4.0
- **Actual Downtime**: 540 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 0.500 | **F1**: 0.667
- **True Positives**: azure_lb, azure_vm
- **False Negatives**: azure_blob, azure_sql

### github-ddos-2018

- **Failed Component**: cdn
- **Actual Affected**: cdn, main_lb, app_server
- **Predicted Affected**: cdn
- **Actual Severity**: major
- **Predicted Severity**: 2.4
- **Actual Downtime**: 20 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.333 | **F1**: 0.500
- **True Positives**: cdn
- **False Negatives**: app_server, main_lb

### fastly-2021-06

- **Failed Component**: cdn
- **Actual Affected**: cdn, dns_resolver
- **Predicted Affected**: cdn, dns_resolver
- **Actual Severity**: critical
- **Predicted Severity**: 8.0
- **Actual Downtime**: 49 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: cdn, dns_resolver

### crowdstrike-2024-07

- **Failed Component**: app_server
- **Actual Affected**: app_server, azure_vm, gce_instance
- **Predicted Affected**: app_server
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 1440 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.333 | **F1**: 0.500
- **True Positives**: app_server
- **False Negatives**: azure_vm, gce_instance

### aws-dynamodb-2015-09

- **Failed Component**: dynamo_db
- **Actual Affected**: dynamo_db, app_server, container_service
- **Predicted Affected**: app_server, container_service, dynamo_db
- **Actual Severity**: major
- **Predicted Severity**: 8.0
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: app_server, container_service, dynamo_db

### gcp-lb-2021-11

- **Failed Component**: main_lb
- **Actual Affected**: main_lb, cdn
- **Predicted Affected**: main_lb
- **Actual Severity**: major
- **Predicted Severity**: 2.4
- **Actual Downtime**: 150 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.500 | **F1**: 0.667
- **True Positives**: main_lb
- **False Negatives**: cdn

### dyn-ddos-2016-10

- **Failed Component**: dns_resolver
- **Actual Affected**: dns_resolver
- **Predicted Affected**: dns_resolver
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 480 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 1.000 | **F1**: 1.000
- **True Positives**: dns_resolver

### aws-kinesis-2020-11

- **Failed Component**: lambda_fn
- **Actual Affected**: lambda_fn, monitoring, app_server, container_service
- **Predicted Affected**: lambda_fn
- **Actual Severity**: critical
- **Predicted Severity**: 2.0
- **Actual Downtime**: 600 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.250 | **F1**: 0.400
- **True Positives**: lambda_fn
- **False Negatives**: app_server, container_service, monitoring

### slack-2022-02

- **Failed Component**: primary_db
- **Actual Affected**: primary_db, app_server, redis, message_queue
- **Predicted Affected**: app_server, primary_db
- **Actual Severity**: major
- **Predicted Severity**: 4.0
- **Actual Downtime**: 300 min
- **Predicted Downtime**: 0.5 min
- **Precision**: 1.000 | **Recall**: 0.500 | **F1**: 0.667
- **True Positives**: app_server, primary_db
- **False Negatives**: message_queue, redis

### aws-ebs-2011-04

- **Failed Component**: app_server
- **Actual Affected**: app_server, primary_db, s3_storage
- **Predicted Affected**: app_server
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 2880 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.333 | **F1**: 0.500
- **True Positives**: app_server
- **False Negatives**: primary_db, s3_storage

### roblox-2021-10

- **Failed Component**: app_server
- **Actual Affected**: app_server, primary_db, redis, message_queue
- **Predicted Affected**: app_server
- **Actual Severity**: critical
- **Predicted Severity**: 2.0
- **Actual Downtime**: 4380 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.250 | **F1**: 0.400
- **True Positives**: app_server
- **False Negatives**: message_queue, primary_db, redis

### azure-ad-2021-03

- **Failed Component**: azure_vm
- **Actual Affected**: azure_vm, azure_sql, azure_blob, app_server
- **Predicted Affected**: azure_vm
- **Actual Severity**: critical
- **Predicted Severity**: 2.0
- **Actual Downtime**: 840 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.250 | **F1**: 0.400
- **True Positives**: azure_vm
- **False Negatives**: app_server, azure_blob, azure_sql

### ovh-fire-2021-03

- **Failed Component**: app_server
- **Actual Affected**: app_server, primary_db, s3_storage
- **Predicted Affected**: app_server
- **Actual Severity**: critical
- **Predicted Severity**: 2.4
- **Actual Downtime**: 43200 min
- **Predicted Downtime**: 5.0 min
- **Precision**: 1.000 | **Recall**: 0.333 | **F1**: 0.500
- **True Positives**: app_server
- **False Negatives**: primary_db, s3_storage
