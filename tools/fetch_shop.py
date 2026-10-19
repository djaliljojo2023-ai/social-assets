"""Download marouchkashop.com product pages and covers, plus logos, into shop/."""
import os, re, json, urllib.request
UA = {'User-Agent': 'Mozilla/5.0 (social-assets fetcher)'}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()
for d in ('shop/pages', 'shop/covers', 'shop/extra'):
    os.makedirs(d, exist_ok=True)
log = {}
for line in open('tools/extra-urls.txt').read().splitlines():
    if not line.strip():
        continue
    url, name = line.split()
    try:
        open(f'shop/extra/{name}', 'wb').write(get(url)); log[name] = 'ok'
    except Exception as e:
        log[name] = str(e)
out = {}
for slug in open('tools/shop-slugs.txt').read().split():
    try:
        html = get(f'https://marouchkashop.com/products/{slug}').decode('utf-8', 'replace')
        open(f'shop/pages/{slug}.html', 'w').write(html)
        m = re.search(r'property="og:image"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+property="og:image"', html)
        imgs = sorted(set(re.findall(r'https://cdn\.youcan\.shop/stores/[^"\'\s)]+/products/[^"\'\s)]+\.(?:png|jpe?g|webp)', html)))
        url = m.group(1) if m else (imgs[0] if imgs else None)
        rec = {'og_image': url, 'images': imgs}
        if url:
            ext = url.rsplit('.', 1)[-1].lower()
            open(f'shop/covers/{slug}.{ext}', 'wb').write(get(url)); rec['file'] = f'covers/{slug}.{ext}'
        out[slug] = rec
    except Exception as e:
        out[slug] = {'error': str(e)}
json.dump({'extra': log, 'products': out}, open('shop/index.json', 'w'), ensure_ascii=False, indent=1)
print(sum(1 for v in out.values() if 'file' in v), 'covers of', len(out), log)
