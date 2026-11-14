import browser_cookie3
import requests

# Try to load cookies from Brave browser
try:
    cj = browser_cookie3.brave(domain_name="pinterest.com")
    cookies = list(cj)
    print(f"Pinterest cookies found in Brave: {len(cookies)}")
    for c in cookies:
        print(f"  Name: {c.name}, Value: {c.value[:50]}..." if len(c.value) > 50 else f"  Name: {c.name}, Value: {c.value}")
except Exception as e:
    print(f"Error loading Brave cookies: {e}")
    # Try without domain restriction
    try:
        cj = browser_cookie3.brave()
        pinterest_cookies = [c for c in cj if 'pinterest' in c.domain.lower()]
        print(f"All cookies: {len(list(cj))}, Pinterest cookies: {len(pinterest_cookies)}")
        for c in pinterest_cookies:
            print(f"  Domain: {c.domain}, Name: {c.name}, Value: {c.value[:50]}...")
    except Exception as e2:
        print(f"Error loading all Brave cookies: {e2}")
