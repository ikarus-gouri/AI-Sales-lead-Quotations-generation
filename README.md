---
title: Catalogue AI
emoji: 🛒
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

AI-powered product catalogue crawler and classifier.

## Overview

This Space runs a Dockerized FastAPI backend for crawling
e-commerce websites and detecting product pages.

## API

### Health Check
`GET /`

### Crawl Website
`POST /crawl?url=<website>&max_pages=20`
