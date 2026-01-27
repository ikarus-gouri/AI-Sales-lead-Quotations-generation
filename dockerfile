# Hugging Face–compatible Python base
FROM python:3.10-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create non-root user (HF best practice)
RUN useradd -m -u 1000 user
USER user

# Set working directory
WORKDIR /app

# Ensure local user installs are available
ENV PATH="/home/user/.local/bin:$PATH"

# Copy only requirements first (better cache)
COPY --chown=user requirements.txt .

# Install dependencies
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY --chown=user . .

# Hugging Face requires port 7860
EXPOSE 7860

# IMPORTANT: app.py must expose `app = FastAPI()`
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
