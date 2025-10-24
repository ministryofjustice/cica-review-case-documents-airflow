FROM ghcr.io/ministryofjustice/analytical-platform-airflow-python-base:1.20.0@sha256:6cfccc9aca038a56a0400a8b382f989ed7ba6868f35e0d94fe564cee3f2e6cd5

ARG MOJAP_IMAGE_VERSION="default"
ENV MOJAP_IMAGE_VERSION=${MOJAP_IMAGE_VERSION}

USER root

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1
ENV HOME=/opt/analyticalplatform
# Set the uv cache directory outside of the project root
ENV UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /opt/analyticalplatform

# Add virtualenv to PATH *before* switching user
ENV PATH="/opt/analyticalplatform/.venv/bin:$PATH"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files (still as root)
COPY uv.lock pyproject.toml README.md ./
COPY src/ingestion_pipeline/ src/ingestion_pipeline/

# Change ownership of all project files to the non-root user
# This user (CONTAINER_UID) is defined in the base image
RUN chown -R ${CONTAINER_UID} /opt/analyticalplatform

# Now, switch to the non-root user
USER ${CONTAINER_UID}

# Create venv and install dependencies *as the non-root user*
# This user will now own the .venv directory
RUN uv venv && \
    uv sync --frozen --no-default-groups && \
    rm -rf ${UV_CACHE_DIR}

# Run the application as the non-root user
CMD ["uv", "run", "python", "src/ingestion_pipeline/main.py"]
