#!/bin/bash
export CLOUDSDK_PYTHON=/Users/ashu/.local/bin/python3.11
/Users/ashu/google-cloud-sdk/bin/gcloud config set project project-833a6a2c-bf8c-4cc2-8f3

# Job 1: Daily Keyword Discovery
/Users/ashu/google-cloud-sdk/bin/gcloud scheduler jobs create http keyword-discovery     --schedule="0 2 * * *"     --uri="https://showup-backend-2bfj.onrender.com/api/seo/research"     --http-method=POST     --message-body='{"keyword": "webinar attendance software", "intent": "commercial"}'     --time-zone="UTC"     --location=us-central1

# Job 2: Generate Content Briefs
/Users/ashu/google-cloud-sdk/bin/gcloud scheduler jobs create http content-briefs     --schedule="0 3 * * *"     --uri="https://showup-backend-2bfj.onrender.com/api/seo/generate"     --http-method=POST     --time-zone="UTC"     --location=us-central1

# Job 3: Generate HTML Pages
/Users/ashu/google-cloud-sdk/bin/gcloud scheduler jobs create http generate-html     --schedule="0 4 * * *"     --uri="https://showup-backend-2bfj.onrender.com/api/seo/generate"     --http-method=POST     --time-zone="UTC"     --location=us-central1

# Job 4: QA Check
/Users/ashu/google-cloud-sdk/bin/gcloud scheduler jobs create http qa-check     --schedule="0 5 * * *"     --uri="https://showup-backend-2bfj.onrender.com/api/seo/performance"     --http-method=GET     --time-zone="UTC"     --location=us-central1

# Job 5: Auto Publish
/Users/ashu/google-cloud-sdk/bin/gcloud scheduler jobs create http auto-publish     --schedule="0 6 * * *"     --uri="https://showup-backend-2bfj.onrender.com/api/seo/publish"     --http-method=POST     --time-zone="UTC"     --location=us-central1
