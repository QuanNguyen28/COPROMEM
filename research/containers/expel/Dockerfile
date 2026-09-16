FROM python:3.9.17-slim@sha256:42a5da33675ec5a692e8cdbb09ffa4e39588c10dd9a96235e543c498484ee18e

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib
COPY requirements-probe.txt /opt/requirements-probe.txt
RUN python -m pip install --no-cache-dir --report /opt/probe-install.json -r /opt/requirements-probe.txt
# Import-only ALFWorld package. Native environments/model embeddings are NOT installed.
RUN python -m pip install --no-cache-dir --no-deps --report /opt/alfworld-import-install.json alfworld==0.3.5
USER 10001:10001
WORKDIR /vendor
ENTRYPOINT ["python"]
