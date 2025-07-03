.PHONY: all install create-index clean ensure-venv-package provision-localstack-resources create-localstack-sqs create-localstack-s3-buckets

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
REQUIREMENTS_FILE := requirements.txt

# Define Python packages needed
PYTHON_PACKAGES := opensearch-py sentence-transformers pip requests_aws4auth awscli

# --- LocalStack Configuration ---
# Make sure your LocalStack instance is running, e.g., via docker-compose up -d
LOCALSTACK_HOST := localhost:4566 # Default LocalStack endpoint
AWS_REGION := eu-west-1            # Recommended to stick to one region for LocalStack, us-east-1 doesn't require LocationConstraint for S3.

# LocalStack resources
SQS_DOCUMENT_QUEUE := cica-document-search
S3_PAGE_BUCKET := document-page-bucket
S3_KTA_DOCUMENTS_BUCKET := local-kta-documents-bucket

all: create-index provision-localstack-resources 

install: $(VENV_DIR) $(REQUIREMENTS_FILE)
	@echo "--- Setting up Python virtual environment and installing dependencies ---"
	$(PIP) install -r $(REQUIREMENTS_FILE)
	@echo "--- Installation complete ---"


ensure-venv-package:
	@if [ "$$(uname -s)" = "Linux" ]; then \
		PYTHON_MINOR_VERSION=$$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "12"); \
		VENV_PACKAGE=python3.$$PYTHON_MINOR_VERSION-venv; \
		echo "Detected Linux OS. Attempting to install $$VENV_PACKAGE if not present..."; \
		echo "You may be prompted for your sudo password."; \
		sudo apt update && sudo apt install -y $$VENV_PACKAGE; \
	elif [ "$$(uname -s)" = "Darwin" ]; then \
		echo "Detected macOS. 'venv' module is typically included with Python 3. Checking python3 availability..."; \
		if ! command -v python3 &> /dev/null; then \
			echo "Error: python3 command not found. Please install Python 3 (e.g., via Homebrew: brew install python)."; \
			exit 1; \
		else \
			echo "python3 found. Proceeding with virtual environment creation."; \
		fi; \
	else \
		echo "Unsupported OS detected: $$(uname -s). Please ensure 'python3 -m venv' functionality is available."; \
	fi

$(VENV_DIR): ensure-venv-package
	@echo "Creating virtual environment at $(VENV_DIR)..."
	python3 -m venv $(VENV_DIR)
	@echo "Virtual environment created."

$(REQUIREMENTS_FILE):
	@echo "Creating requirements.txt..."
	@echo "$(PYTHON_PACKAGES)" | tr ' ' '\n' > $(REQUIREMENTS_FILE)
	@echo "requirements.txt created."

# Create the OpenSearch index
create-index: install
	@echo "--- Creating OpenSearch index ---"
	# Ensure your OpenSearch instance is running via docker-compose before running this.
	# Example: docker-compose up -d
	$(PYTHON) create_opensearch_index.py
	@echo "--- OpenSearch index creation process finished ---"

# --- LocalStack Provisioning Targets ---
provision-localstack-resources: create-localstack-sqs create-localstack-s3-buckets
	@echo "--- All LocalStack resources provisioned successfully ---"

create-localstack-sqs: install
	@echo "--- Creating SQS queue: $(SQS_DOCUMENT_QUEUE) in LocalStack ---"
	@echo "Make sure LocalStack is running (e.g., 'docker-compose up -d')."
	$(PYTHON) -m awscli sqs create-queue \
		--queue-name $(SQS_DOCUMENT_QUEUE) \
		--endpoint-url http://$(LOCALSTACK_HOST) \
		--region $(AWS_REGION)
	@echo "SQS queue '$(SQS_DOCUMENT_QUEUE)' created/ensured."

create-localstack-s3-buckets: install
	@echo "--- Creating S3 bucket: $(S3_PAGE_BUCKET) in LocalStack ---"
	@echo "Make sure LocalStack is running (e.g., 'docker-compose up -d')."
	$(PYTHON) -m awscli s3api create-bucket \
		--bucket $(S3_PAGE_BUCKET) \
		--endpoint-url http://$(LOCALSTACK_HOST) \
		--region $(AWS_REGION) \
		--create-bucket-configuration LocationConstraint=$(AWS_REGION)
	@echo "S3 bucket '$(S3_PAGE_BUCKET)' created/ensured."

	@echo "--- Creating S3 bucket: $(S3_KTA_DOCUMENTS_BUCKET) in LocalStack ---"
	$(PYTHON) -m awscli s3api create-bucket \
		--bucket $(S3_KTA_DOCUMENTS_BUCKET) \
	 	--endpoint-url http://$(LOCALSTACK_HOST) \
	 	--region $(AWS_REGION) \
	 	--create-bucket-configuration LocationConstraint=$(AWS_REGION)
	@echo "S3 bucket '$(S3_KTA_DOCUMENTS_BUCKET)' created/ensured."

# Rule to clean up the virtual environment
clean:
	@echo "--- Cleaning up virtual environment and requirements file ---"
	rm -rf $(VENV_DIR) $(REQUIREMENTS_FILE)
	@echo "--- Clean up complete ---"
