import os
import json
import subprocess
import requests
from PIL import Image, ImageDraw

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"
STORAGE_PINS = r"E:\automation-hub\storage\pins"
DRAFT_FILE = r"E:\automation-hub\storage\drafts\review_batch_60.json"

os.makedirs(STORAGE_PINS, exist_ok=True)
os.makedirs(os.path.dirname(DRAFT_FILE), exist_ok=True)

# 60 Products List
PRODUCTS = [
    {"id": "DS-529103", "title": "Crypto Quantum Blueprint 2026", "category": "Crypto / Trading", "affiliate_url": "https://www.digistore24.com/redir/529103/YOUR_ID/"},
    {"id": "DS-410291", "title": "The AI Affiliate Automation Suite", "category": "Software / AI", "affiliate_url": "https://www.digistore24.com/redir/410291/YOUR_ID/"},
    {"id": "DS-384119", "title": "Project Serenity Crypto Newsletter", "category": "Crypto / Wealth", "affiliate_url": "https://www.digistore24.com/redir/384119/YOUR_ID/"},
    {"id": "DS-492102", "title": "Monetization Matrix: Digital Products", "category": "Biz / Marketing", "affiliate_url": "https://www.digistore24.com/redir/492102/YOUR_ID/"},
    {"id": "DS-319028", "title": "Tube Mastery and Monetization", "category": "Video / Media", "affiliate_url": "https://www.digistore24.com/redir/319028/YOUR_ID/"},
    {"id": "DS-582019", "title": "Print-On-Demand Masterclass", "category": "E-commerce", "affiliate_url": "https://www.digistore24.com/redir/582019/YOUR_ID/"},
    {"id": "DS-439102", "title": "Freelance Copywriting Kickstart", "category": "Skills / Writing", "affiliate_url": "https://www.digistore24.com/redir/439102/YOUR_ID/"},
    {"id": "DS-511029", "title": "Algorithmic Forex Trend Indicator", "category": "Trading / Forex", "affiliate_url": "https://www.digistore24.com/redir/511029/YOUR_ID/"},
    {"id": "DS-492810", "title": "The 1-Page Funnel Formula", "category": "Sales / Web", "affiliate_url": "https://www.digistore24.com/redir/492810/YOUR_ID/"},
    {"id": "DS-382910", "title": "High-Ticket Email Cashflow System", "category": "Email Marketing", "affiliate_url": "https://www.digistore24.com/redir/382910/YOUR_ID/"},
    {"id": "DS-501928", "title": "Notion Life & Business OS Template", "category": "Productivity", "affiliate_url": "https://www.digistore24.com/redir/501928/YOUR_ID/"},
    {"id": "DS-481029", "title": "Faceless TikTok Growth Blueprint", "category": "Social Media", "affiliate_url": "https://www.digistore24.com/redir/481029/YOUR_ID/"},
    {"id": "DS-592019", "title": "SEO Supercharger Guide", "category": "Traffic / SEO", "affiliate_url": "https://www.digistore24.com/redir/592019/YOUR_ID/"},
    {"id": "DS-391029", "title": "Passive Dividend Portfolio Guide", "category": "Personal Finance", "affiliate_url": "https://www.digistore24.com/redir/391029/YOUR_ID/"},
    {"id": "DS-482011", "title": "Canva Template Business in a Box", "category": "Design / Assets", "affiliate_url": "https://www.digistore24.com/redir/482011/YOUR_ID/"},
    {"id": "DS-481920", "title": "Keto Accelerated 28-Day Plan", "category": "Diet / Nutrition", "affiliate_url": "https://www.digistore24.com/redir/481920/YOUR_ID/"},
    {"id": "DS-512903", "title": "Neuromind Pro Focus Protocol", "category": "Brain Health", "affiliate_url": "https://www.digistore24.com/redir/512903/YOUR_ID/"},
    {"id": "DS-419201", "title": "Deep Sleep Optimization Audio", "category": "Wellness / Sleep", "affiliate_url": "https://www.digistore24.com/redir/419201/YOUR_ID/"},
    {"id": "DS-502918", "title": "Plant-Based Muscle Builder", "category": "Fitness / Vegan", "affiliate_url": "https://www.digistore24.com/redir/502918/YOUR_ID/"},
    {"id": "DS-391820", "title": "15-Minute Home Mobility Routine", "category": "Mobility / Rehab", "affiliate_url": "https://www.digistore24.com/redir/391820/YOUR_ID/"},
    {"id": "DS-481902", "title": "Intermittent Fasting Mastery", "category": "Weight Loss", "affiliate_url": "https://www.digistore24.com/redir/481902/YOUR_ID/"},
    {"id": "DS-572019", "title": "Breathwork & Nervous System Reset", "category": "Mind-Body", "affiliate_url": "https://www.digistore24.com/redir/572019/YOUR_ID/"},
    {"id": "DS-491028", "title": "Lean Calisthenics Core Protocol", "category": "Bodyweight", "affiliate_url": "https://www.digistore24.com/redir/491028/YOUR_ID/"},
    {"id": "DS-501920", "title": "Gut Health Revival Cookbook", "category": "Nutrition", "affiliate_url": "https://www.digistore24.com/redir/501920/YOUR_ID/"},
    {"id": "DS-391024", "title": "Natural Testosterone Reset", "category": "Men's Health", "affiliate_url": "https://www.digistore24.com/redir/391024/YOUR_ID/"},
    {"id": "DS-581920", "title": "Somatic Stress Release Guide", "category": "Mental Health", "affiliate_url": "https://www.digistore24.com/redir/581920/YOUR_ID/"},
    {"id": "DS-482019", "title": "Desk Worker Posture Correction", "category": "Ergonomics", "affiliate_url": "https://www.digistore24.com/redir/482019/YOUR_ID/"},
    {"id": "DS-519201", "title": "Herbal Remedies Encyclopedia", "category": "Natural Health", "affiliate_url": "https://www.digistore24.com/redir/519201/YOUR_ID/"},
    {"id": "DS-401928", "title": "Anti-Inflammatory Smoothies Guide", "category": "Drinks / Detox", "affiliate_url": "https://www.digistore24.com/redir/401928/YOUR_ID/"},
    {"id": "DS-592011", "title": "Kettlebell Functional Strength Guide", "category": "Kettlebell", "affiliate_url": "https://www.digistore24.com/redir/592011/YOUR_ID/"},
    {"id": "DS-601928", "title": "The Self-Sufficient Backyard", "category": "Homesteading", "affiliate_url": "https://www.digistore24.com/redir/601928/YOUR_ID/"},
    {"id": "DS-582011", "title": "No Grid Survival Projects", "category": "DIY / Off-Grid", "affiliate_url": "https://www.digistore24.com/redir/582011/YOUR_ID/"},
    {"id": "DS-491029", "title": "The Backyard Greenhouse Blueprint", "category": "Gardening", "affiliate_url": "https://www.digistore24.com/redir/491029/YOUR_ID/"},
    {"id": "DS-392018", "title": "Off-Grid Solar & Battery Setup", "category": "Renewable / DIY", "affiliate_url": "https://www.digistore24.com/redir/392018/YOUR_ID/"},
    {"id": "DS-481023", "title": "Raised Bed Organic Gardening", "category": "Gardening", "affiliate_url": "https://www.digistore24.com/redir/481023/YOUR_ID/"},
    {"id": "DS-502911", "title": "Emergency Food Preservation Bible", "category": "Canning / Pantry", "affiliate_url": "https://www.digistore24.com/redir/502911/YOUR_ID/"},
    {"id": "DS-419208", "title": "DIY Woodworking Small Shop Plans", "category": "Woodworking", "affiliate_url": "https://www.digistore24.com/redir/419208/YOUR_ID/"},
    {"id": "DS-592018", "title": "Rainwater Harvesting & Filtration", "category": "Water Systems", "affiliate_url": "https://www.digistore24.com/redir/592018/YOUR_ID/"},
    {"id": "DS-481924", "title": "Micro-Livestock: Chickens & Quail", "category": "Farming", "affiliate_url": "https://www.digistore24.com/redir/481924/YOUR_ID/"},
    {"id": "DS-391082", "title": "Natural Pest Control Solutions", "category": "Organic Garden", "affiliate_url": "https://www.digistore24.com/redir/391082/YOUR_ID/"},
    {"id": "DS-501924", "title": "Wilderness Bushcraft Survival Guide", "category": "Outdoor / Scout", "affiliate_url": "https://www.digistore24.com/redir/501924/YOUR_ID/"},
    {"id": "DS-492018", "title": "Sourdough & Traditional Bread Guide", "category": "Baking / Food", "affiliate_url": "https://www.digistore24.com/redir/492018/YOUR_ID/"},
    {"id": "DS-582039", "title": "DIY Aquaponics Garden System", "category": "Tech / Garden", "affiliate_url": "https://www.digistore24.com/redir/582039/YOUR_ID/"},
    {"id": "DS-410293", "title": "Emergency First Aid Field Manual", "category": "Preparedness", "affiliate_url": "https://www.digistore24.com/redir/410293/YOUR_ID/"},
    {"id": "DS-501938", "title": "Small-Scale Permaculture Design", "category": "Eco / Garden", "affiliate_url": "https://www.digistore24.com/redir/501938/YOUR_ID/"},
    {"id": "DS-492011", "title": "Sacred Geometry Art Drawing Course", "category": "Art / Geometry", "affiliate_url": "https://www.digistore24.com/redir/492011/YOUR_ID/"},
    {"id": "DS-582910", "title": "Procreate Digital Illustration Hub", "category": "Digital Art", "affiliate_url": "https://www.digistore24.com/redir/582910/YOUR_ID/"},
    {"id": "DS-391028", "title": "Watercolor Botanical Painting Guide", "category": "Fine Art", "affiliate_url": "https://www.digistore24.com/redir/391028/YOUR_ID/"},
    {"id": "DS-502919", "title": "3D Blender Geometry Nodes Starter", "category": "3D Modeling", "affiliate_url": "https://www.digistore24.com/redir/502919/YOUR_ID/"},
    {"id": "DS-419204", "title": "Acoustic Guitar Fingerpicking Method", "category": "Music / Audio", "affiliate_url": "https://www.digistore24.com/redir/419204/YOUR_ID/"},
    {"id": "DS-592010", "title": "Daily Mindfulness & Meditation Habit", "category": "Mindfulness", "affiliate_url": "https://www.digistore24.com/redir/592010/YOUR_ID/"},
    {"id": "DS-481929", "title": "Calligraphy & Modern Hand Lettering", "category": "Crafts", "affiliate_url": "https://www.digistore24.com/redir/481929/YOUR_ID/"},
    {"id": "DS-391049", "title": "Acrylic Pouring & Resin Art Guide", "category": "Crafts / DIY", "affiliate_url": "https://www.digistore24.com/redir/391049/YOUR_ID/"},
    {"id": "DS-501982", "title": "Speed Reading & Memory Retention", "category": "Learning", "affiliate_url": "https://www.digistore24.com/redir/501982/YOUR_ID/"},
    {"id": "DS-492038", "title": "Pixel Art & 2D Game Asset Design", "category": "Game Dev", "affiliate_url": "https://www.digistore24.com/redir/492038/YOUR_ID/"},
    {"id": "DS-582049", "title": "Astrophotography Night Sky Guide", "category": "Photography", "affiliate_url": "https://www.digistore24.com/redir/582049/YOUR_ID/"},
    {"id": "DS-410298", "title": "Clay Sculpting & Character Modeling", "category": "Craft / 3D", "affiliate_url": "https://www.digistore24.com/redir/410298/YOUR_ID/"},
    {"id": "DS-501948", "title": "Sound Design & Beatmaking Blueprint", "category": "Music Production", "affiliate_url": "https://www.digistore24.com/redir/501948/YOUR_ID/"},
    {"id": "DS-482039", "title": "Journaling for Mental Clarity & Goals", "category": "Journaling", "affiliate_url": "https://www.digistore24.com/redir/482039/YOUR_ID/"},
    {"id": "DS-592038", "title": "Chess Strategy: Tactical Patterns", "category": "Strategy", "affiliate_url": "https://www.digistore24.com/redir/592038/YOUR_ID/"}
]

def generate_copy_with_ollama(title, category):
    prompt = f"""You are a Pinterest marketing expert.
Write copy for this offer:
Title: {title}
Category: {category}

Format your output exactly like this:
PIN_TITLE: (Punchy headline under 55 characters)
PIN_DESC: (2 informative sentences with a call to action)
TAGS: (6 viral hashtags)"""

    try:
        res = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }, timeout=90)
        
        text = res.json().get("message", {}).get("content", "")
        pin_title = title[:50]
        pin_desc = f"Discover how {title} can help you achieve results. Click to see the full breakdown!"
        tags = "#guide #trending #productivity"

        for line in text.split("\n"):
            if "PIN_TITLE:" in line:
                pin_title = line.replace("PIN_TITLE:", "").strip()
            elif "PIN_DESC:" in line:
                pin_desc = line.replace("PIN_DESC:", "").strip()
            elif "TAGS:" in line:
                tags = line.replace("TAGS:", "").strip()

        return pin_title, pin_desc, tags
    except Exception as e:
        return title[:50], f"Discover how {title} works. Tap to read the guide!", "#guide #viral #featured"

def render_pin_graphic(prod_id, title, category):
    width, height = 1000, 1500
    temp_img = os.path.join(STORAGE_PINS, f"{prod_id}_temp.png")
    final_img = os.path.join(STORAGE_PINS, f"{prod_id}.png")

    img = Image.new("RGB", (width, height), color="#0B0E14")
    draw = ImageDraw.Draw(img)

    # Borders & cards
    draw.rectangle([(25, 25), (975, 1475)], outline="#CCFF00", width=4)
    draw.rectangle([(50, 60), (950, 180)], fill="#111620", outline="#1E2638")
    draw.text((80, 105), f"TOP RESOURCE // {category.upper()}", fill="#38BDF8")

    draw.rectangle([(50, 240), (950, 1180)], fill="#111620", outline="#1E2638")

    words = title.split()
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > 26:
            lines.append(" ".join(cur[:-1]))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))

    y = 350
    for l in lines[:6]:
        draw.text((90, y), l, fill="#FFFFFF")
        y += 75

    draw.rectangle([(90, 1260), (910, 1390)], fill="#CCFF00")
    draw.text((340, 1310), "CLICK TO EXPLORE", fill="#000000")

    img.save(temp_img, "PNG")

    # FFmpeg lossless scale and verification
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", temp_img, "-vf", "scale=1000:1500", final_img]
    subprocess.run(cmd, check=True)
    if os.path.exists(temp_img):
        os.remove(temp_img)

    return final_img

def main():
    print("=" * 60)
    print("🚀 BATCH ENGINE: GENERATING 60 PRODUCTS LOCALLY VIA OLLAMA")
    print("=" * 60)

    draft_results = []

    for idx, prod in enumerate(PRODUCTS, 1):
        print(f"[{idx}/60] Processing: {prod['title']}")
        
        # 1. Ollama Copywriting (Local RTX GPU)
        pin_title, pin_desc, tags = generate_copy_with_ollama(prod['title'], prod['category'])
        
        # 2. Pillow + FFmpeg 1000x1500 Graphic
        img_path = render_pin_graphic(prod['id'], pin_title, prod['category'])

        entry = {
            "index": idx,
            "id": prod["id"],
            "product_title": prod["title"],
            "category": prod["category"],
            "pin_title": pin_title,
            "pin_description": pin_desc,
            "tags": tags,
            "affiliate_url": prod["affiliate_url"],
            "image_path": img_path,
            "status": "DRAFT_PENDING_REVIEW"
        }
        draft_results.append(entry)

        if idx % 5 == 0 or idx == len(PRODUCTS):
            with open(DRAFT_FILE, "w", encoding="utf-8") as f:
                json.dump(draft_results, f, indent=4)

    print("\n" + "=" * 60)
    print("✅ COMPLETED 60/60 DRAFTS!")
    print(f"📁 Review file saved at: {DRAFT_FILE}")
    print(f"📁 Rendered images saved at: {STORAGE_PINS}")
    print("=" * 60)

if __name__ == "__main__":
    main()
