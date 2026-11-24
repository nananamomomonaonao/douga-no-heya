"""許可リストの各チャンネルの新着フィード(RSS)から動画一覧を集め、videos.js を作る。
1チャンネルあたり最新15本まで。使い方: python3 tools/gen_videos.py（GitHub Actions からは毎日自動で実行）"""
import html, json, os, re, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# channels.js のある場所を基準にする（手元では tools/ の1つ上、GitHub上では同じ階層）
ROOT = HERE if os.path.exists(os.path.join(HERE, "channels.js")) else os.path.dirname(HERE)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36"
src = open(os.path.join(ROOT, "channels.js"), encoding="utf-8").read()
channels = json.loads(re.search(r"window\.CHANNELS = (\[.*\]);", src, re.S).group(1))

# タイトルの除外ワード（ng_words.txt、1行1つの正規表現）
ng_path = os.path.join(ROOT, "ng_words.txt")
ng_pats = [l.strip() for l in open(ng_path, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(ng_path) else []
NG = re.compile("|".join("(?:%s)" % p for p in ng_pats), re.I) if ng_pats else None

def fetch(c):
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + c["id"]
    for attempt in range(3):
        try:
            x = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25).read().decode("utf-8", "replace")
            break
        except Exception:
            x = None
            time.sleep(1 + attempt)
    if x is None:
        return None
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        vid = re.search(r"<yt:videoId>([\w-]{11})</yt:videoId>", e)
        title = re.search(r"<title>(.*?)</title>", e, re.S)
        pub = re.search(r"<published>([^<]+)</published>", e)
        link = re.search(r'<link rel="alternate" href="([^"]+)"', e)
        views = re.search(r'<media:statistics views="(\d+)"', e)
        if not (vid and title and pub):
            continue
        ts = int(datetime.fromisoformat(pub.group(1)).timestamp())
        out.append([vid.group(1), html.unescape(title.group(1)).strip(), ts,
                    1 if link and "/shorts/" in link.group(1) else 0, int(views.group(1)) if views else 0])
    return out

with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(fetch, channels))

ids, videos, failed, dropped = [], [], [], 0
for c, r in zip(channels, res):
    if r is None:
        failed.append(c["name"])
        continue
    if not r:
        continue
    ids.append(c["id"])
    ci = len(ids) - 1
    for v in r:
        if NG and NG.search(v[1]):
            dropped += 1
            continue
        videos.append([v[0], v[1], ci, v[2], v[3], v[4]])

# 取得できたチャンネルが少なすぎるときは、YouTube側に弾かれた可能性が高いので上書きしない
if len(ids) < len(channels) * 0.8:
    raise SystemExit("取得できたチャンネルが %d/%d しかないため、videos.js を更新しません" % (len(ids), len(channels)))

with open(os.path.join(ROOT, "videos.js"), "w", encoding="utf-8") as f:
    f.write("// tools/gen_videos.py が作るファイル。手で編集しない。\n")
    f.write("// VIDEO_CH: チャンネルIDの並び。VIDEOS: [動画ID, タイトル, VIDEO_CHの番号, 公開日時(秒), ショートか, 再生数]\n")
    f.write("window.VIDEOS_AT = %d;\n" % int(time.time()))
    f.write("window.VIDEO_CH = " + json.dumps(ids) + ";\n")
    f.write("window.VIDEOS = [\n" + ",\n".join(json.dumps(v, ensure_ascii=False, separators=(",", ":")) for v in videos) + "\n];\n")
print("チャンネル", len(channels), "取得できた", len(ids), "動画", len(videos), "ショート", sum(v[4] for v in videos))
print("除外ワードで外した動画:", dropped)
print("取得失敗:", failed)
