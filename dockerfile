# Dockerfile
FROM python:3.10-slim

# Create app user
RUN useradd -m -u 1000 user
USER user
WORKDIR /app

# Add local bin to PATH
ENV PATH="/home/user/.local/bin:$PATH"

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose port
EXPOSE 8000

# Run the FastAPI app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
