# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ruff: noqa

"""
This component is derived from the notebook:
https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/use-cases/retrieval-augmented-generation/scalable_rag_with_bigframes.ipynb

It leverages BigQuery for data processing. We also suggest looking at remote functions for enhanced scalability.
"""

from kfp.dsl import Dataset, Output, component


@component(
    base_image="us-docker.pkg.dev/production-ai-template/starter-pack/data_processing:0.2",
    packages_to_install=["pypdf", "google-cloud-storage"]
)
def process_data(
    project_id: str,
    schedule_time: str,
    output_files: Output[Dataset],
    is_incremental: bool = True,
    look_back_days: int = 1,
    chunk_size: int = 1500,
    chunk_overlap: int = 20,
    destination_dataset: str = "stackoverflow_data",
    destination_table: str = "incremental_questions_embeddings",
    deduped_table: str = "questions_embeddings",
    location: str = "us-central1",
    embedding_column: str = "embedding",
    gcs_input_bucket: str = "",
    gcs_input_prefix: str = "kb_documents/",
) -> None:
    """Process StackOverflow questions and answers by:
    1. Fetching data from BigQuery
    2. Converting HTML to markdown
    3. Splitting text into chunks
    4. Generating embeddings
    5. Storing results in BigQuery
    6. Exporting to JSONL

    Args:
        output_files: Output dataset path
        is_incremental: Whether to process only recent data
        look_back_days: Number of days to look back for incremental processing
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        destination_dataset: BigQuery dataset for storing results
        destination_table: Table for storing incremental results
        deduped_table: Table for storing deduplicated results
        location: BigQuery location
    """
    import logging
    from datetime import datetime, timedelta

    import backoff
    import bigframes.ml.llm as llm
    import bigframes.pandas as bpd
    import google.api_core.exceptions
    import swifter
    from google.cloud import bigquery
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from markdownify import markdownify

    # Initialize logging
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Using {swifter} for apply operations.")

    # Initialize clients
    logging.info("Initializing clients...")
    bq_client = bigquery.Client(project=project_id, location=location)
    bpd.options.bigquery.project = project_id
    bpd.options.bigquery.location = location
    logging.info("Clients initialized.")

    # Set date range for data fetch
    schedule_time_dt: datetime = datetime.fromisoformat(
        schedule_time.replace("Z", "+00:00")
    )
    if schedule_time_dt.year == 1970:
        logging.warning(
            "Pipeline schedule not set. Setting schedule_time to current date."
        )
        schedule_time_dt = datetime.now()

    # Note: The following line sets the schedule time 5 years back to allow sample data to be present.
    # For your use case, please comment out the following line to use the actual schedule time.
    schedule_time_dt = schedule_time_dt - timedelta(days=5 * 365)

    START_DATE: datetime = schedule_time_dt - timedelta(
        days=look_back_days
    )  # Start date for data processing window
    END_DATE: datetime = schedule_time_dt  # End date for data processing window

    logging.info(f"Date range set: START_DATE={START_DATE}, END_DATE={END_DATE}")

    def fetch_documents_from_gcs(bucket_name: str, prefix: str) -> list:
        """Fetch document contents from GCS."""
        from google.cloud import storage
        import io
        from pypdf import PdfReader
        
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        
        docs = []
        for blob in blobs:
            if blob.name.endswith(('.md', '.txt')):
                logging.info(f"Processing text {blob.name}...")
                content = blob.download_as_text()
                docs.append({
                    "id": blob.name,
                    "text": content,
                    "metadata": {
                        "source": f"gs://{bucket_name}/{blob.name}",
                        "filename": os.path.basename(blob.name),
                        "last_updated": str(blob.updated)
                    }
                })
            elif blob.name.endswith('.pdf'):
                logging.info(f"Processing PDF {blob.name}...")
                content = blob.download_as_bytes()
                reader = PdfReader(io.BytesIO(content))
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                docs.append({
                    "id": blob.name,
                    "text": text,
                    "metadata": {
                        "source": f"gs://{bucket_name}/{blob.name}",
                        "filename": os.path.basename(blob.name),
                        "last_updated": str(blob.updated)
                    }
                })
        return docs

    def create_table_if_not_exist(
        df: bpd.DataFrame,
        project_id: str,
        dataset_id: str,
        table_id: str,
        partition_column: str,
        location: str = location,
    ) -> None:
        """Create BigQuery table with time partitioning if it doesn't exist."""
        table_schema = bq_client.get_table(df.head(0).to_gbq()).schema
        table = bigquery.Table(
            f"{project_id}.{dataset_id}.{table_id}", schema=table_schema
        )
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY, field=partition_column
        )

        dataset = bigquery.Dataset(f"{project_id}.{dataset_id}")
        dataset.location = location
        bq_client.create_dataset(dataset, exists_ok=True)
        bq_client.create_table(table=table, exists_ok=True)

    # Fetch and preprocess data from GCS
    logging.info("Fetching documents from GCS...")
    # Expecting GCS bucket and prefix to be passed or derived
    # For now, let's assume destination_dataset is used as bucket name or similar
    # In a real setup, we might pass a dedicated gcs_input_path
    raw_docs = fetch_documents_from_gcs(gcs_input_bucket, gcs_input_prefix)
    
    if not raw_docs:
        logging.error("No documents found in GCS. Pipeline will terminate.")
        return

    import pandas as pd
    df_raw = pd.DataFrame(raw_docs)
    
    # Map to expected columns for the rest of the pipeline
    df = bpd.from_pandas(pd.DataFrame({
        "last_edit_date": df_raw["metadata"].apply(lambda x: x["last_updated"]),
        "question_id": df_raw["id"], # Using filename as ID
        "question_text": df_raw["text"],
        "full_text_md": df_raw["text"]
    }))
    
    logging.info(f"Loaded {len(df)} documents.")

    # Split text into chunks
    logging.info("Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )

    df["text_chunk"] = (
        df["full_text_md"]
        .to_pandas()
        .astype(object)
        .swifter.apply(text_splitter.split_text)
    )
    logging.info("Text split into chunks.")

    # Create chunk IDs and explode chunks into rows
    logging.info("Creating chunk IDs and exploding chunks into rows...")
    chunk_ids = [
        str(idx) for text_chunk in df["text_chunk"] for idx in range(len(text_chunk))
    ]
    df = df.explode("text_chunk").reset_index(drop=True)
    df["chunk_id"] = df["question_id"].astype("string") + "__" + chunk_ids
    logging.info("Chunk IDs created and chunks exploded.")

    # Generate embeddings
    logging.info("Generating embeddings...")

    # The first invocation in a new project might fail due to permission propagation.
    @backoff.on_exception(
        backoff.expo, google.api_core.exceptions.InvalidArgument, max_tries=10
    )
    def create_embedder() -> llm.TextEmbeddingGenerator:
        return llm.TextEmbeddingGenerator(model_name="text-embedding-005")

    embedder = create_embedder()

    embeddings_df = embedder.predict(df["text_chunk"])
    logging.info("Embeddings generated.")

    df = df.assign(
        embedding=embeddings_df["ml_generate_embedding_result"],
        embedding_statistics=embeddings_df["ml_generate_embedding_statistics"],
        embedding_status=embeddings_df["ml_generate_embedding_status"],
        creation_timestamp=datetime.now(),
    )

    # Store results in BigQuery
    PARTITION_DATE_COLUMN = "creation_timestamp"

    # Create and populate incremental table
    logging.info("Creating and populating incremental table...")
    create_table_if_not_exist(
        df=df,
        project_id=project_id,
        dataset_id=destination_dataset,
        table_id=destination_table,
        partition_column=PARTITION_DATE_COLUMN,
    )

    if_exists_mode = "append" if is_incremental else "replace"
    df.to_gbq(
        destination_table=f"{destination_dataset}.{destination_table}",
        if_exists=if_exists_mode,
    )
    logging.info("Incremental table created and populated.")

    # Create deduplicated table
    logging.info("Creating deduplicated table...")
    df_questions = bpd.read_gbq(
        f"{destination_dataset}.{destination_table}", use_cache=False
    )
    max_date_df = (
        df_questions.groupby("question_id")["creation_timestamp"].max().reset_index()
    )
    df_questions_dedup = max_date_df.merge(
        df_questions, how="inner", on=["question_id", "creation_timestamp"]
    )

    create_table_if_not_exist(
        df=df_questions_dedup,
        project_id=project_id,
        dataset_id=destination_dataset,
        table_id=deduped_table,
        partition_column=PARTITION_DATE_COLUMN,
    )

    df_questions_dedup.to_gbq(
        destination_table=f"{destination_dataset}.{deduped_table}",
        if_exists="replace",
    )
    logging.info("Deduplicated table created and populated.")

    # Export to JSONL
    logging.info("Exporting to JSONL...")

    export_query = f"""
    SELECT
        chunk_id as id,
        TO_JSON_STRING(STRUCT(
            chunk_id as id,
            embedding as {embedding_column},
            text_chunk as content,
            question_id,
            CAST(creation_timestamp AS STRING) as creation_timestamp,
            CAST(last_edit_date AS STRING) as last_edit_date,
            question_text,
            full_text_md
        )) as json_data
    FROM
        `{project_id}.{destination_dataset}.{deduped_table}`
    WHERE
        chunk_id IS NOT NULL
        AND embedding IS NOT NULL
    """
    export_df_id = bpd.read_gbq(export_query).to_gbq()

    output_files.uri = output_files.uri + "*.jsonl"

    job_config = bigquery.ExtractJobConfig()
    job_config.destination_format = bigquery.DestinationFormat.NEWLINE_DELIMITED_JSON

    extract_job = bq_client.extract_table(
        export_df_id, output_files.uri, job_config=job_config
    )
    extract_job.result()
    logging.info("Exported to JSONL.")
