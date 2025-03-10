# Google Cloud Storage \(GCS\)

## Overview

This destination writes data to GCS bucket.

The Airbyte GCS destination allows you to sync data to cloud storage buckets. Each stream is written to its own directory under the bucket.

## Sync Mode

| Feature | Support | Notes |
| :--- | :---: | :--- |
| Full Refresh Sync | ✅ | Warning: this mode deletes all previously synced data in the configured bucket path. |
| Incremental - Append Sync | ✅ |  |
| Incremental - Deduped History | ❌ | As this connector does not support dbt, we don't support this sync mode on this destination. |
| Namespaces | ❌ | Setting a specific bucket path is equivalent to having separate namespaces. |

## Configuration

| Parameter | Type | Notes |
| :--- | :---: | :--- |
| GCS Bucket Name | string | Name of the bucket to sync data into. |
| GCS Bucket Path | string | Subdirectory under the above bucket to sync the data into. |
| GCS Region | string | See [here](https://cloud.google.com/storage/docs/locations) for all region codes. |
| HMAC Key Access ID | string | HMAC key access ID . The access ID for the GCS bucket. When linked to a service account, this ID is 61 characters long; when linked to a user account, it is 24 characters long. See [HMAC key](https://cloud.google.com/storage/docs/authentication/hmackeys) for details. |
| HMAC Key Secret | string | The corresponding secret for the access ID. It is a 40-character base-64 encoded string. |
| Format | object | Format specific configuration. See below for details. |
| Part Size | integer | Arg to configure a block size. Max allowed blocks by GCS = 10,000, i.e. max stream size = blockSize \* 10,000 blocks. |

Currently, only the [HMAC key](https://cloud.google.com/storage/docs/authentication/hmackeys) is supported. More credential types will be added in the future.

⚠️ Please note that under "Full Refresh Sync" mode, data in the configured bucket and path will be wiped out before each sync. We recommend you to provision a dedicated S3 resource for this sync to prevent unexpected data deletion from misconfiguration. ⚠️

The full path of the output data is:

```text
<bucket-name>/<sorce-namespace-if-exists>/<stream-name>/<upload-date>-<upload-mills>-<partition-id>.<format-extension>
```

For example:

```text
testing_bucket/data_output_path/public/users/2021_01_01_1609541171643_0.csv
↑              ↑                ↑      ↑     ↑          ↑             ↑ ↑
|              |                |      |     |          |             | format extension
|              |                |      |     |          |             partition id
|              |                |      |     |          upload time in millis
|              |                |      |     upload date in YYYY-MM-DD
|              |                |      stream name
|              |                source namespace (if it exists)
|              bucket path
bucket name
```

Please note that the stream name may contain a prefix, if it is configured on the connection.

The rationales behind this naming pattern are: 1. Each stream has its own directory. 2. The data output files can be sorted by upload time. 3. The upload time composes of a date part and millis part so that it is both readable and unique.

Currently, each data sync will only create one file per stream. In the future, the output file can be partitioned by size. Each partition is identifiable by the partition ID, which is always 0 for now.

## Output Schema

Each stream will be outputted to its dedicated directory according to the configuration. The complete datastore of each stream includes all the output files under that directory. You can think of the directory as equivalent of a Table in the database world.

* Under Full Refresh Sync mode, old output files will be purged before new files are created.
* Under Incremental - Append Sync mode, new output files will be added that only contain the new data.

### Avro

[Apache Avro](https://avro.apache.org/) serializes data in a compact binary format. Currently, the Airbyte S3 Avro connector always uses the [binary encoding](http://avro.apache.org/docs/current/spec.html#binary_encoding), and assumes that all data records follow the same schema.

#### Configuration

Here is the available compression codecs:

* No compression
* `deflate`
  * Compression level
    * Range `[0, 9]`. Default to 0.
    * Level 0: no compression & fastest.
    * Level 9: best compression & slowest.
* `bzip2`
* `xz`
  * Compression level
    * Range `[0, 9]`. Default to 6.
    * Level 0-3 are fast with medium compression.
    * Level 4-6 are fairly slow with high compression.
    * Level 7-9 are like level 6 but use bigger dictionaries and have higher memory requirements. Unless the uncompressed size of the file exceeds 8 MiB, 16 MiB, or 32 MiB, it is waste of memory to use the presets 7, 8, or 9, respectively.
* `zstandard`
  * Compression level
    * Range `[-5, 22]`. Default to 3.
    * Negative levels are 'fast' modes akin to `lz4` or `snappy`.
    * Levels above 9 are generally for archival purposes.
    * Levels above 18 use a lot of memory.
  * Include checksum
    * If set to `true`, a checksum will be included in each data block.
* `snappy`

#### Data schema

Under the hood, an Airbyte data stream in Json schema is first converted to an Avro schema, then the Json object is converted to an Avro record. Because the data stream can come from any data source, the Json to Avro conversion process has arbitrary rules and limitations. Learn more about how source data is converted to Avro and the current limitations [here](https://docs.airbyte.io/understanding-airbyte/json-avro-conversion).

### CSV

Like most of the other Airbyte destination connectors, usually the output has three columns: a UUID, an emission timestamp, and the data blob. With the CSV output, it is possible to normalize \(flatten\) the data blob to multiple columns.

| Column | Condition | Description |
| :--- | :--- | :--- |
| `_airbyte_ab_id` | Always exists | A uuid assigned by Airbyte to each processed record. |
| `_airbyte_emitted_at` | Always exists. | A timestamp representing when the event was pulled from the data source. |
| `_airbyte_data` | When no normalization \(flattening\) is needed, all data reside under this column as a json blob. |  |
| root level fields | When root level normalization \(flattening\) is selected, the root level fields are expanded. |  |

For example, given the following json object from a source:

```json
{
  "user_id": 123,
  "name": {
    "first": "John",
    "last": "Doe"
  }
}
```

With no normalization, the output CSV is:

| `_airbyte_ab_id` | `_airbyte_emitted_at` | `_airbyte_data` |
| :--- | :--- | :--- |
| `26d73cde-7eb1-4e1e-b7db-a4c03b4cf206` | 1622135805000 | `{ "user_id": 123, name: { "first": "John", "last": "Doe" } }` |

With root level normalization, the output CSV is:

| `_airbyte_ab_id` | `_airbyte_emitted_at` | `user_id` | `name` |
| :--- | :--- | :--- | :--- |
| `26d73cde-7eb1-4e1e-b7db-a4c03b4cf206` | 1622135805000 | 123 | `{ "first": "John", "last": "Doe" }` |

### JSON Lines \(JSONL\)

[Json Lines](https://jsonlines.org/) is a text format with one JSON per line. Each line has a structure as follows:

```json
{
  "_airbyte_ab_id": "<uuid>",
  "_airbyte_emitted_at": "<timestamp-in-millis>",
  "_airbyte_data": "<json-data-from-source>"
}
```

For example, given the following two json objects from a source:

```json
[
  {
    "user_id": 123,
    "name": {
      "first": "John",
      "last": "Doe"
    }
  },
  {
    "user_id": 456,
    "name": {
      "first": "Jane",
      "last": "Roe"
    }
  }
]
```

They will be like this in the output file:

```text
{ "_airbyte_ab_id": "26d73cde-7eb1-4e1e-b7db-a4c03b4cf206", "_airbyte_emitted_at": "1622135805000", "_airbyte_data": { "user_id": 123, "name": { "first": "John", "last": "Doe" } } }
{ "_airbyte_ab_id": "0a61de1b-9cdd-4455-a739-93572c9a5f20", "_airbyte_emitted_at": "1631948170000", "_airbyte_data": { "user_id": 456, "name": { "first": "Jane", "last": "Roe" } } }
```

### Parquet

#### Configuration

The following configuration is available to configure the Parquet output:

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `compression_codec` | enum | `UNCOMPRESSED` | **Compression algorithm**. Available candidates are: `UNCOMPRESSED`, `SNAPPY`, `GZIP`, `LZO`, `BROTLI`, `LZ4`, and `ZSTD`. |
| `block_size_mb` | integer | 128 \(MB\) | **Block size \(row group size\)** in MB. This is the size of a row group being buffered in memory. It limits the memory usage when writing. Larger values will improve the IO when reading, but consume more memory when writing. |
| `max_padding_size_mb` | integer | 8 \(MB\) | **Max padding size** in MB. This is the maximum size allowed as padding to align row groups. This is also the minimum size of a row group. |
| `page_size_kb` | integer | 1024 \(KB\) | **Page size** in KB. The page size is for compression. A block is composed of pages. A page is the smallest unit that must be read fully to access a single record. If this value is too small, the compression will deteriorate. |
| `dictionary_page_size_kb` | integer | 1024 \(KB\) | **Dictionary Page Size** in KB. There is one dictionary page per column per row group when dictionary encoding is used. The dictionary page size works like the page size but for dictionary. |
| `dictionary_encoding` | boolean | `true` | **Dictionary encoding**. This parameter controls whether dictionary encoding is turned on. |

These parameters are related to the `ParquetOutputFormat`. See the [Java doc](https://www.javadoc.io/doc/org.apache.parquet/parquet-hadoop/1.12.0/org/apache/parquet/hadoop/ParquetOutputFormat.html) for more details. Also see [Parquet documentation](https://parquet.apache.org/documentation/latest/#configurations) for their recommended configurations \(512 - 1024 MB block size, 8 KB page size\).

#### Data schema

Under the hood, an Airbyte data stream in Json schema is first converted to an Avro schema, then the Json object is converted to an Avro record, and finally the Avro record is outputted to the Parquet format. Because the data stream can come from any data source, the Json to Avro conversion process has arbitrary rules and limitations. Learn more about how source data is converted to Avro and the current limitations [here](https://docs.airbyte.io/understanding-airbyte/json-avro-conversion).

## Getting started

### Requirements

1. Allow connections from Airbyte server to your GCS cluster \(if they exist in separate VPCs\).
2. An GCP bucket with credentials \(for the COPY strategy\).

### Setup guide

* Fill up GCS info
  * **GCS Bucket Name**
    * See [this](https://cloud.google.com/storage/docs/creating-buckets) to create an S3 bucket.
  * **GCS Bucket Region**
  * **HMAC Key Access ID**
    * See [this](https://cloud.google.com/storage/docs/authentication/hmackeys) on how to generate an access key.
    * We recommend creating an Airbyte-specific user or service account. This user or account will require read and write permissions to objects in the bucket.
  * **Secret Access Key**
    * Corresponding key to the above access ID.
* Make sure your GCS bucket is accessible from the machine running Airbyte.
  * This depends on your networking setup.
  * The easiest way to verify if Airbyte is able to connect to your GCS bucket is via the check connection tool in the UI.

## CHANGELOG

| Version | Date | Pull Request | Subject |
| :--- | :--- | :--- | :--- |
| 0.1.17 | 2021-12-21 | [\#8574](https://github.com/airbytehq/airbyte/pull/8574) | Added namespace to Avro and Parquet record types |
| 0.1.16 | 2021-12-20 | [\#8974](https://github.com/airbytehq/airbyte/pull/8974) | Release a new version to ensure there is no excessive logging. |
| 0.1.15 | 2021-12-03 | [\#8386](https://github.com/airbytehq/airbyte/pull/8386) | Add new GCP regions |
| 0.1.14 | 2021-12-01 | [\#7732](https://github.com/airbytehq/airbyte/pull/7732) | Support timestamp in Avro and Parquet |
| 0.1.13 | 2021-11-03 | [\#7288](https://github.com/airbytehq/airbyte/issues/7288) | Support Json `additionalProperties`. |
| 0.1.2 | 2021-09-12 | [\#5720](https://github.com/airbytehq/airbyte/issues/5720) | Added configurable block size for stream. Each stream is limited to 10,000 by GCS |
| 0.1.1 | 2021-08-26 | [\#5296](https://github.com/airbytehq/airbyte/issues/5296) | Added storing gcsCsvFileLocation property for CSV format. This is used by destination-bigquery \(GCS Staging upload type\) |
| 0.1.0 | 2021-07-16 | [\#4329](https://github.com/airbytehq/airbyte/pull/4784) | Initial release. |
