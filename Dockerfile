FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transfer_plan_app.py .

# Cloud Run injects $PORT (8080). Streamlit must bind 0.0.0.0, not localhost,
# or the container will fail its health check.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "streamlit run transfer_plan_app.py \
  --server.port=${PORT} \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --server.enableCORS=false \
  --server.enableXsrfProtection=true \
  --server.fileWatcherType=none \
  --browser.gatherUsageStats=false"]
