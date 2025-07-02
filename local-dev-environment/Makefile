.PHONY: all install create-index clean ensure-venv-package

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
REQUIREMENTS_FILE := requirements.txt

# Define Python packages needed
PYTHON_PACKAGES := opensearch-py sentence-transformers pip requests_aws4auth

all: create-index

# Rule to create a virtual environment and install dependencies
install: $(VENV_DIR) $(REQUIREMENTS_FILE)
	@echo "--- Setting up Python virtual environment and installing dependencies ---"
	$(PIP) install -r $(REQUIREMENTS_FILE)
	@echo "--- Installation complete ---"

# New target to ensure the python3-venv package is installed on Linux
ensure-venv-package:
	@if [ "$$(uname -s)" = "Linux" ]; then \
		PYTHON_MINOR_VERSION=$$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "12"); \
		VENV_PACKAGE=python3.$$PYTHON_MINOR_VERSION-venv; \
		echo "Detected Linux OS. Attempting to install $$VENV_PACKAGE if not present..."; \
		echo "You may be prompted for your sudo password."; \
		sudo apt update && sudo apt install -y $$VENV_PACKAGE; \
	fi

$(VENV_DIR): ensure-venv-package
	@echo "Creating virtual environment at $(VENV_DIR)..."
	python3 -m venv $(VENV_DIR)
	@echo "Virtual environment created."

$(REQUIREMENTS_FILE):
	@echo "Creating requirements.txt..."
	@echo "$(PYTHON_PACKAGES)" | tr ' ' '\n' > $(REQUIREMENTS_FILE)
	@echo "requirements.txt created."

# Rule to create the OpenSearch index
create-index: install
	@echo "--- Creating OpenSearch index ---"
	# Ensure your OpenSearch instance is running via docker-compose before running this.
	# Example: docker-compose up -d
	$(PYTHON) create_opensearch_index.py
	@echo "--- OpenSearch index creation process finished ---"

# Rule to clean up the virtual environment
clean:
	@echo "--- Cleaning up virtual environment and requirements file ---"
	rm -rf $(VENV_DIR) $(REQUIREMENTS_FILE)
	@echo "--- Clean up complete ---"
