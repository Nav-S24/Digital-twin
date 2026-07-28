FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Phase 3's code resolves data paths relative to its own working directory
# ("../data/...", "Output.csv"), so the layout on disk (data/ next to
# project/) is preserved as-is rather than flattened.
COPY data ./data
COPY project ./project
RUN pip install --no-cache-dir -r ./project/requirements.txt

WORKDIR /app/project
EXPOSE 8003
CMD ["uvicorn", "phase2_pipeline:app", "--host", "0.0.0.0", "--port", "8003"]
