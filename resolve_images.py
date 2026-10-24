import requests
import json

headers = {'User-Agent': 'ContemporaryArtBot/1.0 (https://github.com/polarstar718/contemporary-art-telegram-bot; contact: test@gmail.com)'}

def get_image_url(query):
    url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={query}&gsrlimit=1&prop=imageinfo&iiprop=url&format=json"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        pages = r.json().get('query', {}).get('pages', {})
        for pid, pdata in pages.items():
            infos = pdata.get('imageinfo', [])
            if infos:
                return infos[0].get('url')
    except Exception as e:
        pass
    return None

test_queries = [
    "The Weather Project Olafur Eliasson Tate",
    "Your rainbow panorama Olafur Eliasson",
    "Do Ho Suh Fallen Star",
    "Yayoi Kusama Pumpkin Naoshima",
    "Anish Kapoor Cloud Gate Chicago"
]

for q in test_queries:
    img = get_image_url(q)
    print(q, "-->", img)
