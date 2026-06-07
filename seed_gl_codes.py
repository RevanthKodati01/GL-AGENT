from database import get_connection

GL_CODES = [
    ("Travel", "Travel", "Flights, hotels, rideshare, transportation",
     "uber,lyft,delta,united,american air,marriott,hotel,airbnb,airline,taxi"),
    ("Meals", "Meals & Entertainment", "Restaurants, coffee, client dinners",
     "starbucks,coffee,restaurant,cafe,blue bottle,doordash,grubhub,bar,grill"),
    ("Software", "Software & SaaS", "Cloud services, subscriptions, software",
     "aws,google cloud,zoom,dropbox,linkedin,apple.com,digitalocean,github,slack,notion"),
    ("Office", "Office Supplies", "Supplies, equipment, workspace",
     "amazon,amzn,office depot,staples,wework,supplies"),
    ("Marketing", "Marketing & Advertising", "Ads, campaigns, promotion",
     "facebk,facebook,meta,google ads,instagram,tiktok ads,ads"),
    ("Utilities", "Utilities", "Internet, phone, electricity",
     "comcast,verizon,at&t,electric,water,internet,phone"),
    ("Professional", "Professional Services", "Legal, accounting, consulting",
     "law,legal,accounting,consulting,advisory"),
    ("Contractor", "Contractor Payments", "Payments to contractors and freelancers",
     ""),
    ("Equipment", "Equipment & Hardware", "Computers, machinery, hardware",
     "dell,apple store,lenovo,hardware,equipment"),
    ("Uncategorized", "Uncategorized", "Could not be confidently categorized",
     ""),
]

def seed():
    conn = get_connection()
    cursor = conn.cursor()
    for code, name, desc, keywords in GL_CODES:
        cursor.execute("""
            INSERT OR IGNORE INTO gl_codes (gl_code, category_name, description, keyword_rules)
            VALUES (?, ?, ?, ?)
        """, (code, name, desc, keywords))
    conn.commit()
    conn.close()
    print(f"Seeded {len(GL_CODES)} GL codes")

if __name__ == "__main__":
    seed()