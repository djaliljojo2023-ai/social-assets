"""Publish due posts from marouchka/schedule.json to the Facebook Page and Instagram.

Runs from .github/workflows/publish.yml every 10 minutes. Secrets:
  META_PAGE_TOKEN  Page access token (pages_manage_posts, pages_read_engagement,
                   instagram_basic, instagram_content_publish)
  META_PAGE_ID     numeric Facebook Page id
Env: DRY_RUN=1 prints what would be published. CATCHUP_HOURS (default 6) skips posts older than that.
Published ids are recorded in marouchka/published.json so nothing is posted twice.
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

V = 'v21.0'
G = f'https://graph.facebook.com/{V}/'
TOKEN = os.environ.get('META_PAGE_TOKEN', '')
PAGE = os.environ.get('META_PAGE_ID', '')
DRY = os.environ.get('DRY_RUN') == '1'
CATCHUP = timedelta(hours=float(os.environ.get('CATCHUP_HOURS', '6')))
SCHED, DONE = 'marouchka/schedule.json', 'marouchka/published.json'


def call(path, params=None, post=True, url=None, headers=None):
    params = dict(params or {}, access_token=TOKEN)
    data = urllib.parse.urlencode(params).encode()
    u = url or G + path
    req = urllib.request.Request(u if post else u + '?' + data.decode(), data=data if post else None,
                                 method='POST' if post else 'GET', headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{e.code} {path or u}: {e.read().decode()[:400]}')


def ig_wait(cid):
    for _ in range(60):
        st = call(cid, {'fields': 'status_code'}, post=False).get('status_code')
        if st == 'FINISHED':
            return
        if st in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f'instagram container {cid} {st}')
        time.sleep(10)
    raise RuntimeError(f'instagram container {cid} not ready')


def ig_publish(ig, kind, media, caption):
    p = {'caption': caption} if kind != 'story' else {}
    if kind == 'video':
        p.update(media_type='REELS', video_url=media, share_to_feed='true')
    elif kind == 'story':
        p.update(media_type='STORIES', **({'video_url': media} if media.endswith('.mp4') else {'image_url': media}))
    else:
        p['image_url'] = media
    cid = call(f'{ig}/media', p)['id']
    ig_wait(cid)
    return call(f'{ig}/media_publish', {'creation_id': cid})['id']


def fb_publish(kind, media, caption):
    if kind == 'image':
        return call(f'{PAGE}/photos', {'url': media, 'message': caption})['id']
    if kind == 'story':
        pid = call(f'{PAGE}/photos', {'url': media, 'published': 'false'})['id']
        return call(f'{PAGE}/photo_stories', {'photo_id': pid}).get('post_id', pid)
    # reel: start, upload by URL, finish
    vid = call(f'{PAGE}/video_reels', {'upload_phase': 'start'})['video_id']
    call(None, {}, url=f'https://rupload.facebook.com/video-upload/{V}/{vid}',
         headers={'Authorization': f'OAuth {TOKEN}', 'file_url': media})
    call(f'{PAGE}/video_reels', {'upload_phase': 'finish', 'video_id': vid, 'video_state': 'PUBLISHED', 'description': caption})
    return vid


def main():
    if not TOKEN or not PAGE:
        print('META_PAGE_TOKEN / META_PAGE_ID secrets are not set yet; nothing to do.')
        return
    items = json.load(open(SCHED))
    done = json.load(open(DONE)) if os.path.exists(DONE) else {}
    now = datetime.now(timezone.utc)
    ig = call(PAGE, {'fields': 'instagram_business_account'}, post=False).get('instagram_business_account', {}).get('id')
    for it in items:
        at = datetime.fromisoformat(it['at'])
        if at > now or now - at > CATCHUP:
            continue
        for net in it.get('networks', ['facebook', 'instagram']):
            key = f"{it['id']}:{net}"
            if key in done:
                continue
            print(('DRY ' if DRY else '') + 'publish', key, it['kind'], it['media'])
            if DRY:
                continue
            try:
                if net == 'facebook':
                    done[key] = fb_publish(it['kind'], it['media'], it.get('caption', ''))
                elif net == 'instagram' and ig:
                    done[key] = ig_publish(ig, it['kind'], it['media'], it.get('caption', ''))
            except Exception as e:
                print('  failed:', e)
            json.dump(done, open(DONE, 'w'), indent=1)


if __name__ == '__main__':
    main()
