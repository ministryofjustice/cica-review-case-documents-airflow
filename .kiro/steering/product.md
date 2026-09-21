# Product Overview

This is the **CICA Review Case Documents Airflow Ingestion Pipeline** — a backend service for the Criminal Injuries Compensation Authority (CICA) document search system.

## What It Does

- Ingests CICA case documents from S3
- Performs OCR via AWS Textract to extract text
- Chunks extracted text using configurable strategies (word-stream, layout, or sentence-splitting)
- Generates vector embeddings via AWS Bedrock (Titan Embed Text v2)
- Stores text chunks and metadata in OpenSearch (vector database)
- Creates page images and stores them in S3

## How It's Used

This pipeline feeds data into a UI application (cica-review-case-documents) that enables CICA case workers to:
- Query the vector database with natural language search
- View highlighted search results against page images

## Current Status

The project is in active private beta. Features and chunking strategies are still evolving.

Each run drains the SQS document queue across multiple batches, up to a configurable ceiling (`MAX_BATCHES_PER_RUN`), stopping when the queue is empty (a single empty long-poll) or the ceiling is reached. Messages that repeatedly fail are redriven to a Dead Letter Queue (DLQ) after `SQS_MAX_RECEIVE_COUNT` (default 3) receives, so poison documents are not retried indefinitely.

## Domain Context

- Documents are associated with case references matching the pattern `NN-[7|8]NNNNN` (e.g., `26-711111`)
- Documents have correspondence types (e.g., "TC19 - ADDITIONAL INFO REQUEST")
- Each document is uniquely identified by a deterministic UUID derived from filename, correspondence type, and case ref
- The pipeline runs on the Ministry of Justice Analytical Platform using Airflow
