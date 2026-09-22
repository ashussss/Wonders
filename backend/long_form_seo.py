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
    """Generates a specific section (to manage token limits)."""
    print(f"DEBUG: Generating section: {section_title}")
    prompt = f"""
    Write a 300-word authoritative section titled '{section_title}' for a blog post about '{keyword}'.

    Context: {context}

    CRITICAL E-E-A-T GUIDELINES (Follow strictly):
    - Tone: Skeptical, technical, professional, direct.
    - DO NOT use AI fluff: "revolutionary," "unlock," "in the ever-evolving landscape," "transformative."
    - Expertise: Write as a veteran marketer who understands webinar ROI.
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="qwen/qwen3.8-27b",
            max_tokens=800,
        )
        print(f"DEBUG: Section {section_title} generated successfully.")
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"DEBUG: Error generating section {section_title}: {e}")
        raise e

def generate_long_form_content(keyword):
    """Generates content in sections to bypass token limits."""
    sections = [
        ("Introduction: The Webinar Attendance Problem", "Focus on the high drop-off rates in traditional tools like Zoom."),
        ("Why Traditional Tools Fail", "Discuss interactivity limitations and lack of automation."),
        ("The 'Attendance-First' Philosophy: ShowupAI.live", "Explain how ShowupAI.live handles automation and engagement pre-webinar."),
        ("ShowupAI.live vs Zoom: Quantifiable Results", "Focus on attendance boost metrics."),
        ("Conclusion", "Summary and CTA.")
    ]

    full_content = ""
    for title, context in sections:
        print(f"Generating section: {title}...")
        try:
            section_content = generate_seo_section(keyword, title, context)
            full_content += f"\n\n## {title}\n\n{section_content}"
            time.sleep(12)  # Throttling to respect OTPM limits
        except Exception as e:
            print(f"Error generating section {title}: {e}")
            time.sleep(15)
    return full_content

def run_pseo():
    keywords = ["Best Zoom alternatives for high attendance webinars"]
    for kw in keywords:
        print(f"Generating long-form content for: {kw}...")
        try:
            content = generate_long_form_content(kw)
            db.blog_posts.insert_one({
                "keyword": kw,
                "content": content,
                "published": False,
                "slug": kw.lower().replace(" ", "-")
            })
            print(f"Successfully saved long-form content to MongoDB: {kw}")
        except Exception as e:
            print(f"Error generating long-form for {kw}: {e}")

if __name__ == "__main__":
    run_pseo()
