#!/usr/bin/env python3
"""Публикация article.md в Telegraph через API (только стандартная библиотека).

  python3 tools/telegraph.py check   <папка>   # разобрать статью, проверить фото, ничего не публиковать
  python3 tools/telegraph.py publish <папка>   # создать страницу или обновить свою

Формат article.md: '# Заголовок', 'author: Имя | ссылка', '### Подзаголовок',
абзацы через пустую строку, ссылки [текст](url), фото '![подпись](папка/файл.jpg)'.
Фото берутся из этого репозитория с ветки main, поэтому перед publish их нужно запушить.
Токен Telegraph хранится в .telegraph-token (в .gitignore, в git не попадает).
Адрес созданной страницы пишется в <папка>/telegraph.json.
"""
import json, re, sys, os, urllib.request, urllib.parse

REPO_RAW = "https://raw.githubusercontent.com/mashainfethie-web/aqua-incognita-media/main/"
API = "https://api.telegra.ph/"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".telegraph-token")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def inline(text):
    nodes, pos = [], 0
    for m in LINK.finditer(text):
        if m.start() > pos:
            nodes.append(text[pos:m.start()])
        nodes.append({"tag": "a", "attrs": {"href": m.group(2)}, "children": [m.group(1)]})
        pos = m.end()
    if pos < len(text):
        nodes.append(text[pos:])
    return nodes


def parse(path):
    title, author, author_url, content, images = None, None, None, [], []
    for block in open(path, encoding="utf-8").read().split("\n\n"):
        b = block.strip()
        if not b:
            continue
        if b.startswith("# "):
            title = b[2:].strip()
        elif b.startswith("author:"):
            parts = [p.strip() for p in b[7:].split("|")]
            author, author_url = parts[0], (parts[1] if len(parts) > 1 else None)
        elif b.startswith("### "):
            content.append({"tag": "h3", "children": inline(b[4:].strip())})
        elif b.startswith("#### "):
            content.append({"tag": "h4", "children": inline(b[5:].strip())})
        elif b.startswith("> "):
            content.append({"tag": "blockquote", "children": inline(b[2:].strip())})
        else:
            m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", b)
            if m:
                src = m.group(2) if m.group(2).startswith("http") else REPO_RAW + m.group(2)
                images.append(src)
                fig = [{"tag": "img", "attrs": {"src": src}}]
                if m.group(1):
                    fig.append({"tag": "figcaption", "children": [m.group(1)]})
                content.append({"tag": "figure", "children": fig})
            else:
                content.append({"tag": "p", "children": inline(" ".join(b.split("\n")))})
    if not title:
        sys.exit("Нет строки '# Заголовок'")
    return title, author, author_url, content, images


def api(method, **params):
    data = urllib.parse.urlencode({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                                   for k, v in params.items() if v is not None}).encode()
    with urllib.request.urlopen(urllib.request.Request(API + method, data=data), timeout=30) as r:
        res = json.load(r)
    if not res.get("ok"):
        sys.exit(f"Telegraph {method}: {res.get('error')}")
    return res["result"]


def check_images(images):
    bad = []
    for src in images:
        try:
            req = urllib.request.Request(src, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if not r.headers.get("Content-Type", "").startswith("image/"):
                    bad.append(src)
        except Exception:
            bad.append(src)
    return bad


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "publish"):
        sys.exit(__doc__)
    cmd, folder = sys.argv[1], sys.argv[2].rstrip("/")
    title, author, author_url, content, images = parse(os.path.join(folder, "article.md"))
    size = len(json.dumps(content, ensure_ascii=False).encode())
    print(f"Заголовок: {title}\nБлоков: {len(content)}, фото: {len(images)}, размер: {size} байт (лимит 64 КБ)")
    bad = check_images(images)
    if bad:
        sys.exit("Фото не открываются (не запушены?):\n" + "\n".join(bad))
    print("Все фото открываются.")
    if cmd == "check":
        return
    token = open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else None
    if not token:
        token = api("createAccount", short_name="AquaIncognita", author_name=author, author_url=author_url)["access_token"]
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
        os.chmod(TOKEN_FILE, 0o600)
    state_file = os.path.join(folder, "telegraph.json")
    state = json.load(open(state_file)) if os.path.exists(state_file) else {}
    common = dict(access_token=token, title=title, author_name=author, author_url=author_url, content=content)
    try:
        page = api("editPage", path=state["path"], **common) if state.get("path") else api("createPage", **common)
    except SystemExit as e:
        if "PAGE_ACCESS_DENIED" not in str(e):
            raise
        page = api("createPage", **common)  # страница принадлежит другому аккаунту: делаем новую
        print("Старую страницу этим токеном править нельзя, создана новая.")
    json.dump({"path": page["path"], "url": page["url"]}, open(state_file, "w"), ensure_ascii=False, indent=2)
    print("Опубликовано:", page["url"])


if __name__ == "__main__":
    main()
