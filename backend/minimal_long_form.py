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

def generate_seo_section(keyword, section_title, context):
    prompt = f"""
    Write a 200-word authoritative section '{section_title}' for '{keyword}'.
    Tone: Technical, professional, direct.
    No marketing fluff.
    Context: {context}
    """

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="qwen/qwen3.8-27b",
        max_tokens=600,
    )
    return chat_completion.choices[0].message.content

def run_pseo():
    kw = "Best Zoom alternatives for high attendance webinars"
    sections = [
        ("Intro", "Webinar drop-off problem."),
        ("Why Zoom Fails", "Lack of engagement tools."),
        ("ShowupAI USP", "Automation of attendance."),
        ("Results", "Attendance metrics."),
        ("Conclusion", "Summary.")
    ]

    full_content = ""
    for title, ctx in sections:
        try:
            full_content += f"\n\n## {title}\n\n{generate_seo_section(kw, title, ctx)}"
            time.sleep(20) # Conservative sleep
        except Exception as e:
            print(f"Error {title}: {e}")

    db.blog_posts.insert_one({"keyword": kw, "content": full_content})
    print("Done.")

if __name__ == "__main__":
    run_pseo()
