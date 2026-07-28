FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build the vector index at image build time so the container is
# immediately queryable on startup rather than lazily embedding on first
# request. Uses the offline TF-IDF fallback by default since the Docker
# build environment may not have internet access to huggingface.co; set
# EMBEDDING_BACKEND=huggingface (and rebuild, or exec build_vectordb.py
# again at runtime) for production-quality semantic retrieval once
# internet access to huggingface.co is available.
ENV EMBEDDING_BACKEND=tfidf
ENV SIMILARITY_THRESHOLD=1.1
RUN python build_vectordb.py

EXPOSE 8006
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8006"]
