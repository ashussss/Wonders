import os
import time
from groq import Groq
from pymongo import MongoClient
from dotenv import load_dotenv

# Load env variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

client = Groq(api_key=GROQ_API_KEY)
db = MongoClient(MONGO_URI).wonders_db

def generate_seo_content(keyword):
    # E-E-A-T Optimized Prompt emphasizing Attendance Rate USP
    prompt = f"""
    Write an authoritative, 200-word blog post targeting: '{keyword}'.

    CORE MESSAGE (THE USP):
    - ShowupAI.live is NOT just another 'interactive webinar tool'.
    - It is an 'Attendance-First' webinar platform.
    - Focus heavily on how it solves the massive 'webinar drop-off' problem that tools like Zoom/GoToWebinar fail to fix.
    - Explain that the industry standard is low attendance, but showupai.live changes that math with smart automation.

    CRITICAL E-E-A-T GUIDELINES (Follow strictly):
    - Tone: Skeptical, technical, professional, direct.
    - DO NOT use AI fluff: "revolutionary," "unlock," "in the ever-evolving landscape," "transformative."
    - Expertise: Write as a veteran marketer who understands webinar ROI.
    - Structure: Use clear H2/H3 headers. Include a 'Why Traditional Tools Fail' section and a 'How ShowupAI.live Boosts Attendance Rates' section.
    """

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="qwen/qwen3.8-27b",
        max_tokens=900,
    )
    return chat_completion.choices[0].message.content

def run_pseo():
    keywords = [
        "Best Zoom alternatives for high attendance webinars",
        "How to increase webinar attendance rates",
        "Showupai.live vs Zoom: Solving webinar drop-off",
        "Best automated webinar software for lead generation"
    ]
    for kw in keywords:
        print(f"Generating content for: {kw}...")
        try:
            content = generate_seo_content(kw)
            db.blog_posts.insert_one({
                "keyword": kw,
                "content": content,
                "published": False,
                "slug": kw.lower().replace(" ", "-")
            })
            print(f"Successfully saved to MongoDB: {kw}")
            time.sleep(10)
        except Exception as e:
            print(f"Error generating for {kw}: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_pseo()