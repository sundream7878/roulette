import urllib.request
try:
    url = "https://roulette-asgj.onrender.com/guest"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read().decode('utf-8')
        for line in html.split('\n'):
            if 'event-title-display' in line or 'prize-item' in line:
                print(line.strip())
except Exception as e:
    print(f"Error fetching URL: {e}")
