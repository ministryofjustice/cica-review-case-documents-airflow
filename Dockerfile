FROM ghcr.io/ministryofjustice/analytical-platform-airflow-python-base:1.19.0@sha256:594f9d28b5b53ad55f96dce790774dccc93db892a167bcbd832bb9a06fea0e1b


# Switch to root user to install packages
USER root                 
                       
# Copy requirements.txt
# TODO change this to poetry?
COPY requirements.txt requirements.txt 

# Copy application code
COPY src/ .

# Install requirements
RUN <<EOF
pip install --no-cache-dir --requirement requirements.txt
EOF

# Switch back to non-root user (analyticalplatform)
USER ${CONTAINER_UID}

# Execute main.py script
ENTRYPOINT ["python3", "main.py"]
