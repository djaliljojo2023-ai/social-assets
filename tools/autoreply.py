"""Auto-reply to new comments on the Marouchka Facebook page and Instagram account.

Runs from .github/workflows/autoreply.yml. Secrets:
  META_PAGE_TOKEN    long-lived Page access token (pages_read_engagement,
                     pages_manage_engagement, instagram_basic, instagram_manage_comments)
  META_PAGE_ID       numeric Facebook Page id
  ANTHROPIC_API_KEY  optional; when set, replies are written by Claude, otherwise by keyword rules
Env: DRY_RUN=1 prints replies without posting. DAYS=14 limits how far back to look.
"""
import json, os, random, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

G = 'https://graph.facebook.com/v21.0/'
TOKEN = os.environ.get('META_PAGE_TOKEN', '')
PAGE = os.environ.get('META_PAGE_ID', '')
DRY = os.environ.get('DRY_RUN') == '1'
DAYS = int(os.environ.get('DAYS', '14'))
SINCE = datetime.now(timezone.utc) - timedelta(days=DAYS)

FACTS = """دار ماروشكا للطباعة والنشر والتوزيع، تاقوفت، أم البواقي، الجزائر.
الموقع الرسمي: editionsmarouchka.com — المتجر: marouchkashop.com (الدفع عند الاستلام).
واتساب: 0697717050.
نشارك في الصالون الدولي للكتاب بالجزائر 2026، من 29 أكتوبر إلى 7 نوفمبر، جناح فلسطين C77.
نستقبل مخطوطات الكتّاب للنشر (التواصل عبر واتساب)."""

RULES = [
    (r'سعر|بكم|ثمن|الثمن|prix|price|combien|كم ثمن', [
        'مرحبًا بك 🌷 تجد السعر في متجرنا marouchkashop.com والدفع عند الاستلام. لأي استفسار راسلنا على واتساب 0697717050',
        'أهلًا وسهلًا 🌷 الأسعار متوفرة على marouchkashop.com، ويمكنك أيضًا مراسلتنا على واتساب 0697717050']),
    (r'طلب|اطلب|أطلب|نطلب|توصيل|يوصل|ولاي|commande|livraison|commander|order', [
        'مرحبًا 🌷 يمكنك الطلب مباشرة من marouchkashop.com والدفع عند الاستلام، أو عبر واتساب 0697717050',
        'أهلًا بك 🌷 الطلب سهل من متجرنا marouchkashop.com والدفع عند الاستلام. للمساعدة: واتساب 0697717050']),
    (r'صالون|معرض|جناح|sila|salon|وين|أين|فين|العنوان|مكان', [
        'ننتظركم في الصالون الدولي للكتاب بالجزائر 2026 من 29 أكتوبر إلى 7 نوفمبر، جناح فلسطين C77 🌷',
        'أهلًا بك 🌷 تجدنا في الصالون الدولي للكتاب بالجزائر 2026، جناح فلسطين C77، من 29 أكتوبر إلى 7 نوفمبر']),
    (r'نشر|انشر|أنشر|ننشر|مخطوط|كتابي|روايتي|ديواني|publier|publish|édition', [
        'يسعدنا ذلك 🌷 أرسل لنا تفاصيل مخطوطك على واتساب 0697717050 وسنتواصل معك',
        'مرحبًا بك 🌷 دار ماروشكا ترحب بالكتّاب. راسلنا على واتساب 0697717050 بخصوص النشر']),
]
THANKS = ['شكرًا لك 🌷 سعداء بمتابعتك لدار ماروشكا', 'شكرًا على تفاعلك 🌷 اقرأ بشغف مع دار ماروشكا',
          'نورتنا 🌷 شكرًا لمتابعتك', 'شكرًا جزيلًا 🌷 دمت قارئًا شغوفًا']


def api(path, params=None, post=False):
    params = dict(params or {}, access_token=TOKEN)
    data = urllib.parse.urlencode(params).encode()
    url = G + path if post else G + path + '?' + data.decode()
    req = urllib.request.Request(url, data=data if post else None, method='POST' if post else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{e.code} {path}: {e.read().decode()[:300]}')


def pages(path, params):
    out = api(path, params)
    while True:
        yield from out.get('data', [])
        nxt = out.get('paging', {}).get('next')
        if not nxt:
            return
        with urllib.request.urlopen(nxt, timeout=30) as r:
            out = json.load(r)


def claude_reply(text, post_text):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return None
    body = {'model': 'claude-haiku-5-5', 'max_tokens': 300,
            'system': 'أنت مسؤول صفحة دار ماروشكا على مواقع التواصل. اكتب ردًا قصيرًا ولطيفًا (جملة أو جملتان) على التعليق، '
                      'بلهجة عربية فصحى بسيطة، أو بلغة التعليق إن كان بالفرنسية أو الإنجليزية. استعمل فقط المعلومات التالية ولا تخترع أسعارًا أو أرقامًا أو أعدادًا:\n'
                      + FACTS + '\nإن كان التعليق شتمًا أو سبامًا أو لا يستحق ردًا فأجب بكلمة SKIP فقط.',
            'messages': [{'role': 'user', 'content': f'المنشور: {post_text[:500]}\n\nالتعليق: {text}'}]}
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(body).encode(), method='POST',
                                 headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)['content'][0]['text'].strip()
    except Exception as e:
        print('claude error, falling back to rules:', e)
        return None


def make_reply(text, post_text=''):
    r = claude_reply(text, post_text)
    if r:
        return None if r.strip().upper().startswith('SKIP') else r
    for pat, opts in RULES:
        if re.search(pat, text or '', re.I):
            return random.choice(opts)
    return random.choice(THANKS)


def recent(ts):
    return datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc) >= SINCE


def facebook():
    n = 0
    for post in pages(f'{PAGE}/posts', {'fields': 'id,message,created_time', 'limit': 25}):
        if not recent(post['created_time']):
            break
        for c in pages(f"{post['id']}/comments", {'fields': 'id,message,from,created_time,comments.limit(50){from}', 'filter': 'toplevel', 'limit': 100}):
            if c.get('from', {}).get('id') == PAGE:
                continue
            if any(x.get('from', {}).get('id') == PAGE for x in c.get('comments', {}).get('data', [])):
                continue
            reply = make_reply(c.get('message', ''), post.get('message', ''))
            if not reply:
                continue
            print('FB', c['id'], repr(c.get('message', ''))[:80], '->', reply)
            if not DRY:
                api(f"{c['id']}/comments", {'message': reply}, post=True)
                time.sleep(2)
            n += 1
    return n


def instagram():
    ig = api(PAGE, {'fields': 'instagram_business_account'}).get('instagram_business_account', {}).get('id')
    if not ig:
        print('no Instagram business account linked to the page')
        return 0
    me = api(ig, {'fields': 'username'})['username']
    n = 0
    for m in pages(f'{ig}/media', {'fields': 'id,caption,timestamp', 'limit': 25}):
        if not recent(m['timestamp']):
            break
        for c in pages(f"{m['id']}/comments", {'fields': 'id,text,username,replies{username}', 'limit': 50}):
            if c.get('username') == me or any(x.get('username') == me for x in c.get('replies', {}).get('data', [])):
                continue
            reply = make_reply(c.get('text', ''), m.get('caption', ''))
            if not reply:
                continue
            reply = f"@{c['username']} {reply}" if c.get('username') else reply
            print('IG', c['id'], repr(c.get('text', ''))[:80], '->', reply)
            if not DRY:
                api(f"{c['id']}/replies", {'message': reply}, post=True)
                time.sleep(2)
            n += 1
    return n


if __name__ == '__main__':
    if not TOKEN or not PAGE:
        print('META_PAGE_TOKEN / META_PAGE_ID secrets are not set yet; nothing to do.')
        sys.exit(0)
    total = 0
    for fn in (facebook, instagram):
        try:
            total += fn()
        except Exception as e:
            print(fn.__name__, 'error:', e)
    print(('would reply' if DRY else 'replied'), total)
