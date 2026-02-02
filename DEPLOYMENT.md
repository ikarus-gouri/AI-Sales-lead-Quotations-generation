# Hugging Face Spaces Deployment Guide

## Prerequisites

1. A Hugging Face account (free at [huggingface.co](https://huggingface.co))
2. Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Deployment Steps

### 1. Create a New Space

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Fill in:
   - **Space name**: `configurator-extractor` (or your choice)
   - **License**: MIT
   - **Select SDK**: Docker
   - **Space hardware**: CPU basic (free tier works)

### 2. Upload Files

Upload these files to your Space:
- `Dockerfile`
- `requirements.txt`
- `app.py`
- `yayy.py`
- `page_navigator.py`
- `README.md`

### 3. Configure Space

In your Space settings:
- **SDK**: Docker
- **Docker template**: Custom
- **Secrets** (optional): You can add `GEMINI_API_KEY` as a secret if you want users to use a shared key

### 4. Build and Deploy

The Space will automatically build using the Dockerfile. This may take 5-10 minutes.

### 5. Test Your Space

Once built, the Gradio interface will be available at:
`https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME`

## Local Testing

### Test with Docker

```bash
# Build the Docker image
docker build -t configurator-extractor .

# Run the container
docker run -p 7860:7860 configurator-extractor
```

Then visit: http://localhost:7860

### Test without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the app
python app.py
```

## Troubleshooting

### Build Issues

1. **Playwright installation fails**: The Dockerfile includes all necessary dependencies
2. **Out of memory**: Increase Space hardware to CPU basic or better
3. **Timeout during build**: This is normal for first build; retry if it fails

### Runtime Issues

1. **Browser won't launch**: Ensure `--no-sandbox` flag is set (already in code)
2. **Extraction hangs**: Reduce max_iterations or check the URL
3. **API errors**: Verify Gemini API key is valid

## Cost

- **HF Space**: Free tier available (CPU basic)
- **Gemini API**: Free tier: 15 requests/minute, 1500 requests/day
- **Total**: $0 for typical usage

## Updating Your Space

1. Edit files locally
2. Push to your Space repository (git or web interface)
3. Space will automatically rebuild

## Tips

- Start with CPU basic hardware (free)
- Upgrade to better hardware only if needed
- Monitor your Gemini API usage
- Set reasonable max_iterations (10-20)

## Support

For issues:
- Check logs in HF Space settings
- Review Playwright documentation
- Verify Gemini API quota

## Example Space Configuration

```yaml
title: Configurator Option Extractor
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
```

This file (if named `README.md` with YAML header) will configure your Space metadata.
