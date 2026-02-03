# Hugging Face–compatible Python base
FROM python:3.10-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ----------------------------
# System deps required by Chromium
# ----------------------------
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libxkbcommon0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libxrandr2 \
    libxdamage1 \
    libxcomposite1 \
    libxfixes3 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    libx11-6 \
    fonts-liberation \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Create non-root user (HF best practice)
# ----------------------------
RUN useradd -m -u 1000 user
USER user

# Set working directory
WORKDIR /app

# Ensure local user installs are available
ENV PATH="/home/user/.local/bin:$PATH"

# ----------------------------
# Install Python deps
# ----------------------------
COPY --chown=user requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ----------------------------
# 🔥 Install Playwright browser
# ----------------------------
RUN playwright install chromium

# Copy the rest of the project
COPY --chown=user . .

# Hugging Face requires port 7860
EXPOSE 7860

# IMPORTANT: app.py must expose `app = FastAPI()`
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
