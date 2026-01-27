# Dockerfile for Hugging Face Spaces
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Create non-root user (required by HF Spaces)
RUN useradd -m -u 1000 user
RUN chown -R user:user /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY --chown=user:user requirements.txt .

# Switch to non-root user
USER user

# Add user's local bin to PATH
ENV PATH="/home/user/.local/bin:$PATH"

# Install Python dependencies
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=user:user . .

# Create results directory
RUN mkdir -p results

# Expose port 7860 (HF Spaces standard)
EXPOSE 7860

# Set environment variable for port
ENV PORT=7860

# Run the FastAPI application
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]