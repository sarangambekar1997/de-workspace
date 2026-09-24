# Airflow with the lab's extra Python packages baked in.
# Installing packages at container start (_PIP_ADDITIONAL_REQUIREMENTS) is slower and less reproducible.
FROM apache/airflow:slim-3.3.2-python3.12

COPY requirements.txt /requirements.txt
# The slim image has no database drivers: add the Postgres extra, pinned to the image's Airflow version
RUN pip install --no-cache-dir "apache-airflow[postgres]==${AIRFLOW_VERSION}" -r /requirements.txt
