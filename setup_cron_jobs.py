import requests
import json
import time

API_TOKEN = 'sW3+dIImjpZVjnBH+tjLYdN8q43cFO5MCAyqd7JquyU='
BASE_URL = 'https://api.cron-job.org'
HEADERS = {
    'Authorization': f'Bearer {API_TOKEN}',
    'Content-Type': 'application/json'
}

jobs = [
    {
        "title": "Keyword Discovery",
        "url": "https://showup-backend-2bfj.onrender.com/api/seo/research",
        "method": "POST",
        "body": '{"keyword": "webinar attendance software", "intent": "commercial"}',
        "schedule": "0 2 * * *"
    },
    {
        "title": "Content Briefs",
        "url": "https://showup-backend-2bfj.onrender.com/api/seo/generate",
        "method": "POST",
        "body": '{"keyword": "webinar attendance software", "intent": "informational"}',
        "schedule": "0 3 * * *"
    },
    {
        "title": "Generate HTML",
        "url": "https://showup-backend-2bfj.onrender.com/api/seo/generate",
        "method": "POST",
        "body": '{"keyword": "webinar attendance software", "intent": "commercial"}',
        "schedule": "0 4 * * *"
    },
    {
        "title": "QA Check",
        "url": "https://showup-backend-2bfj.onrender.com/api/seo/performance",
        "method": "GET",
        "body": "",
        "schedule": "0 5 * * *"
    },
    {
        "title": "Auto Publish",
        "url": "https://showup-backend-2bfj.onrender.com/api/seo/publish",
        "method": "POST",
        "body": "{}",
        "schedule": "0 6 * * *"
    }
]

for job in jobs:
    payload = {
        "cronjob": {
            "title": job["title"],
            "url": job["url"],
            "enabled": True,
            "schedule": {
                "timezone": "UTC",
                "expiresAt": 0,
                "hours": [int(job["schedule"].split()[1])],
                "minutes": [int(job["schedule"].split()[0])],
                "mdays": [-1],
                "months": [-1],
                "wdays": [-1]
            },
            "request": {
                "method": job["method"],
                "body": job["body"] or ""
            }
        }
    }
    
    # POST to create
    response = requests.post(f"{BASE_URL}/jobs", headers=HEADERS, json=payload)
    print(f"[{response.status_code}] Created {job['title']}: {response.text}")
    time.sleep(1)

