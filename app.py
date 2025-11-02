# app.py — Matties ana sayfa + gönderi/yorum + foto/video yükleme + admin kullanıcı silme
# Hızlı Çalıştırma:
#   python -m venv venv && source venv/bin/activate
#   pip install flask flask_sqlalchemy sqlalchemy werkzeug
#   export ADMIN_USERNAME="itu-itis22-yilmaz20"   # opsiyonel
#   python app.py

import os, re, uuid
from flask import (
    Flask, request, redirect, url_for, session, render_template_string,
    send_from_directory, Response, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

# -------------------- DİZİN & UYGULAMA --------------------
BASE_DIR = os.path.abspath(os.getcwd())
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
MEDIA_DIR  = os.path.join(UPLOAD_DIR, "media")
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR,  exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "CHANGE_THIS_SECRET")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB
db = SQLAlchemy(app)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "itu-itis22-yilmaz20")

# -------------------- MEDYA TİPLERİ --------------------
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".ogg", ".m4v", ".mov"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}

def is_image(path): return os.path.splitext(path)[1].lower() in IMAGE_EXT
def is_video(path): return os.path.splitext(path)[1].lower() in VIDEO_EXT
def is_audio(path): return os.path.splitext(path)[1].lower() in AUDIO_EXT

def save_media(file_storage, target_dir):
    safe = secure_filename(file_storage.filename)
    stem, ext = os.path.splitext(safe)
    unique = f"{stem}_{uuid.uuid4().hex[:8]}{ext.lower()}"
    file_storage.save(os.path.join(target_dir, unique))
    return unique

# -------------------- MODELLER --------------------
class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar        = db.Column(db.String(120))

class Post(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    html_content = db.Column(db.Text)

class Comment(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id      = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    html_content = db.Column(db.Text)

class DirectMessage(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    to_user_id   = db.Column(db.Integer, db.ForeignKey("user.id"))
    html_content = db.Column(db.Text)

class Friendship(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("user.id"))
    friend_id = db.Column(db.Integer, db.ForeignKey("user.id"))

# -------------------- YARDIMCI FONKSİYONLAR --------------------
def _delete_file_safely(full_path: str):
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except OSError:
        pass

def _collect_media_paths_from_html(html: str):
    """HTML içinden /uploads/... veya /media/... ile başlayan src'leri döndürür (tam path)."""
    if not html:
        return []
    paths = []
    for rel in re.findall(r'src=[\'"](/(?:uploads|media)/[^\'"]+)[\'"]', html):
        rel_norm = os.path.normpath(rel).lstrip("/")  # -> uploads/xyz.png
        full = os.path.join(BASE_DIR, rel_norm)
        # Sadece uploads/ ya da media/ altında olanları kabul et
        up = os.path.join(BASE_DIR, "uploads")
        md = os.path.join(BASE_DIR, "media")
        if full.startswith(up) or full.startswith(md):
            paths.append(full)
    return paths

# -------------------- HTML (GÖMÜLÜ) --------------------
INDEX_HTML = """
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Matties</title>
<style>
  body{font-family:Arial;margin:0;background:#eef7ee}
  header{background:#90ee90;padding:10px;display:flex;justify-content:space-between;align-items:center}
  .wrap{max-width:900px;margin:20px auto;background:#fff;padding:15px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
  .post{border-bottom:1px solid #eee;padding:10px 0}
  .media{max-width:100%;height:auto;border-radius:6px}
  form.inline{display:inline}
  .topnav a{margin-right:10px}
  textarea{width:100%;min-height:80px}
  .cwrap{margin-left:12px;border-left:3px solid #eee;padding-left:12px}
  .small{color:#666;font-size:.9em}
</style>
</head>
<body>
<header>
  <strong>Matties</strong>
  <div class="topnav">
    {% if me %}
      <span class="small">Giriş: <b>{{ me.username }}</b></span> |
      <a href="/logout">Çıkış</a> |
      <a href="/admin/users">Admin</a>
    {% else %}
      <a href="/login/{{ admin }}">Admin olarak giriş</a>
      <a href="/login/ali">ali olarak giriş</a>
    {% endif %}
  </div>
</header>

<div class="wrap">
  {% if me %}
  <h3>Gönderi paylaş</h3>
  <form method="POST" action="{{ url_for('create_post') }}" enctype="multipart/form-data">
    <textarea name="text" placeholder="Ne düşünüyorsun?"></textarea>
    <div>
      <label>Fotoğraf: <input type="file" name="photo" accept="image/*"></label>
      <label>Video/Ses: <input type="file" name="media" accept="video/*,audio/*"></label>
    </div>
    <button type="submit">Paylaş</button>
  </form>
  {% else %}
  <p>Gönderi paylaşmak için giriş yap.</p>
  {% endif %}
</div>

<div class="wrap">
  <h3>Akış</h3>
  {% if not posts %}
    <p>Henüz gönderi yok.</p>
  {% endif %}
  {% for p, author, comments in posts %}
  <div class="post">
    <div class="small"><b>@{{ author.username }}</b> — #{{ p.id }}</div>
    <div class="content">{{ p.html_content|safe }}</div>

    <div class="cwrap">
      <div class="small"><b>Yorumlar:</b></div>
      {% for c, cuser in comments %}
        <div class="small">• <b>@{{ cuser.username }}</b>: {{ c.html_content|safe }}</div>
      {% endfor %}

      {% if me %}
      <form class="inline" method="POST" action="{{ url_for('add_comment', post_id=p.id) }}" enctype="multipart/form-data" style="display:block;margin-top:6px;">
        <input name="text" placeholder="Yorum yaz..." style="width:60%">
        <input type="file" name="media" accept="image/*,video/*,audio/*">
        <button type="submit">Yorum ekle</button>
      </form>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Admin - Kullanıcı Silme</title>
<style>
  body { font-family: Arial; background: #f5f5f5; }
  table { border-collapse: collapse; width: 70%; margin: 30px auto; background: white; }
  th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
  th { background: #90ee90; }
  button { background: #ff5555; color: white; border: none; padding: 5px 10px; cursor: pointer; }
  button:hover { background: #cc0000; }
  .small { font-size: 0.9em; color: #666; }
</style>
</head>
<body>
  <h2 style="text-align:center;">Kullanıcı Listesi (Admin: {{ admin_name }})</h2>
  <div style="width:70%; margin:0 auto 10px auto;">
    <p class="small">Giriş yapan: {{ current_user or '(yok)' }} — <a href="/logout">Çıkış</a> — <a href="/">Ana sayfa</a></p>
  </div>
  <table>
    <tr><th>Kullanıcı Adı</th><th>Avatar</th><th>İşlem</th></tr>
    {% for u in users %}
    <tr>
      <td>{{ u.username }}</td>
      <td>{{ u.avatar or '-' }}</td>
      <td>
        {% if u.username != admin_name %}
        <form method="POST" action="{{ url_for('admin_delete_user', username=u.username) }}" onsubmit="return confirm('{{ u.username }} silinsin mi?');">
          <button type="submit">Sil</button>
        </form>
        {% else %}
          (Admin)
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""

# -------------------- ROUTE’LAR: Giriş/Çıkış --------------------
@app.route("/login/<username>")
def fake_login(username):
    # DEMO amaçlı — gerçek projede normal login kullan
    u = User.query.filter_by(username=username).first()
    if not u:
        return "Kullanıcı bulunamadı.", 404
    session["user"] = username
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))

def current_user():
    uname = session.get("user")
    return User.query.filter_by(username=uname).first() if uname else None

# -------------------- ROUTE: Ana Sayfa --------------------
@app.route("/")
def index():
    me = current_user()

    # Postları çek + yorumlarıyla birlikte bas
    all_posts = Post.query.order_by(Post.id.desc()).all()
    bundle = []
    for p in all_posts:
        author = User.query.get(p.user_id)
        cs = Comment.query.filter_by(post_id=p.id).order_by(Comment.id.asc()).all()
        comments = [(c, User.query.get(c.user_id)) for c in cs]
        bundle.append((p, author, comments))

    return render_template_string(INDEX_HTML, me=me, admin=ADMIN_USERNAME, posts=bundle)

# -------------------- ROUTE: Gönderi Oluştur --------------------
@app.route("/post", methods=["POST"])
def create_post():
    me = current_user()
    if not me:
        return redirect(url_for("index"))

    text  = (request.form.get("text") or "").strip()
    photo = request.files.get("photo")
    media = request.files.get("media")

    parts = []
    if text:
        parts.append(text.replace("\n","<br>"))
    if photo and photo.filename:
        if not is_image(photo.filename): return "Sadece resim yükleyin.", 400
        img_name = save_media(photo, UPLOAD_DIR)
        parts.append(f"<img class='media' src='/uploads/{img_name}' alt=''>")
    if media and media.filename:
        ext = os.path.splitext(media.filename)[1].lower()
        if ext not in VIDEO_EXT.union(AUDIO_EXT): return "Desteklenmeyen medya.", 400
        media_name = save_media(media, MEDIA_DIR)
        if ext in VIDEO_EXT:
            parts.append(f"<video class='media' controls preload='metadata' src='/media/{media_name}'></video>")
        else:
            parts.append(f"<audio controls src='/media/{media_name}'></audio>")

    if not parts:
        return redirect(url_for("index"))

    db.session.add(Post(user_id=me.id, html_content="<br>".join(parts)))
    db.session.commit()
    return redirect(url_for("index"))

# -------------------- ROUTE: Yorum Ekle --------------------
@app.route("/comment/<int:post_id>", methods=["POST"])
def add_comment(post_id):
    me = current_user()
    if not me:
        return redirect(url_for("index"))
    target = Post.query.get(post_id)
    if not target:
        return "Gönderi bulunamadı.", 404

    text  = (request.form.get("text") or "").strip()
    media = request.files.get("media")

    parts = []
    if text: parts.append(text.replace("\n","<br>"))
    if media and media.filename:
        ext = os.path.splitext(media.filename)[1].lower()
        if ext in IMAGE_EXT:
            name = save_media(media, UPLOAD_DIR); parts.append(f"<img class='media' src='/uploads/{name}' alt=''>")
        elif ext in VIDEO_EXT:
            name = save_media(media, MEDIA_DIR);  parts.append(f"<video class='media' controls preload='metadata' src='/media/{name}'></video>")
        elif ext in AUDIO_EXT:
            name = save_media(media, MEDIA_DIR);  parts.append(f"<audio controls src='/media/{name}'></audio>")
        else:
            return "Desteklenmeyen medya.", 400

    if parts:
        db.session.add(Comment(user_id=me.id, post_id=post_id, html_content="<br>".join(parts)))
        db.session.commit()

    return redirect(url_for("index"))

# -------------------- ROUTE: Dosya Servisi --------------------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

def partial_response(path, mimetype):
    if not os.path.exists(path): abort(404)
    file_size = os.path.getsize(path)
    range_header = request.headers.get('Range', None)
    if not range_header:
        with open(path, 'rb') as f:
            data = f.read()
        return Response(data, 200, mimetype=mimetype, direct_passthrough=True)

    try:
        _, rng = range_header.split('=')
        start_end = rng.split('-')
        start = int(start_end[0]) if start_end[0] else 0
        end = int(start_end[1]) if len(start_end) > 1 and start_end[1] else file_size - 1
        start = max(0, start); end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})
    except Exception:
        with open(path, 'rb') as f:
            return Response(f.read(), 200, mimetype=mimetype, direct_passthrough=True)

    length = end - start + 1
    def generate():
        with open(path, 'rb') as f:
            f.seek(start)
            remaining = length
            chunk = 64 * 1024
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data: break
                remaining -= len(data)
                yield data
    headers = {"Content-Range": f"bytes {start}-{end}/{file_size}",
               "Accept-Ranges": "bytes",
               "Content-Length": str(length)}
    return Response(generate(), 206, mimetype=mimetype, headers=headers)

@app.route("/media/<path:filename>")
def serve_media(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXT:
        mimetype = "video/mp4" if ext in {".mp4",".m4v"} else ("video/webm" if ext==".webm" else "video/ogg")
    elif ext in AUDIO_EXT:
        mimetype = "audio/mpeg" if ext==".mp3" else ("audio/wav" if ext==".wav" else ("audio/mp4" if ext==".m4a" else "audio/ogg"))
    else:
        mimetype = "application/octet-stream"
    return partial_response(os.path.join(MEDIA_DIR, filename), mimetype)

# -------------------- ADMIN: Kullanıcı Silme --------------------
ADMIN_ONLY = lambda: session.get("user") == ADMIN_USERNAME

ADMIN_PAGE = "/admin/users"

@app.route("/admin/users")
def admin_users():
    if not ADMIN_ONLY():
        return "Yetkisiz erişim.", 403
    users = User.query.order_by(User.username).all()
    return render_template_string(ADMIN_HTML, users=users, admin_name=ADMIN_USERNAME, current_user=session.get("user"))

@app.route("/admin/delete_user/<username>", methods=["POST"])
def admin_delete_user(username):
    if not ADMIN_ONLY():
        return "Yetkisiz erişim.", 403

    target = User.query.filter_by(username=username).first()
    if not target:
        return "Kullanıcı bulunamadı.", 404
    if target.username == ADMIN_USERNAME:
        return "Admin kullanıcısını silemezsin.", 400

    # 1) Avatar
    if target.avatar:
        _delete_file_safely(os.path.join(AVATAR_DIR, target.avatar))

    # 2) Post/yorum/DM içindeki medya dosyalarını toplayıp sil
    for p in Post.query.filter_by(user_id=target.id).all():
        for fp in _collect_media_paths_from_html(p.html_content):
            _delete_file_safely(fp)
    for c in Comment.query.filter_by(user_id=target.id).all():
        for fp in _collect_media_paths_from_html(c.html_content):
            _delete_file_safely(fp)
    dms = DirectMessage.query.filter(or_(DirectMessage.from_user_id==target.id,
                                         DirectMessage.to_user_id==target.id)).all()
    for m in dms:
        for fp in _collect_media_paths_from_html(m.html_content):
            _delete_file_safely(fp)

    # 3) İlişkili verileri sil
    Friendship.query.filter(or_(Friendship.user_id==target.id, Friendship.friend_id==target.id)).delete(synchronize_session=False)
    Comment.query.filter_by(user_id=target.id).delete(synchronize_session=False)
    DirectMessage.query.filter(or_(DirectMessage.from_user_id==target.id, DirectMessage.to_user_id==target.id)).delete(synchronize_session=False)
    Post.query.filter_by(user_id=target.id).delete(synchronize_session=False)

    # 4) Kullanıcıyı sil
    db.session.delete(target)
    db.session.commit()
    return redirect(ADMIN_PAGE)

# -------------------- DB OLUŞTUR & ÖRNEKLER --------------------
with app.app_context():
    db.create_all()
    if not User.query.first():
        pwd = generate_password_hash("1234")
        db.session.add_all([
            User(username=ADMIN_USERNAME, password_hash=pwd, avatar=None),
            User(username="ali", password_hash=pwd, avatar=None),
            User(username="veli", password_hash=pwd, avatar=None),
        ])
        db.session.commit()
        # Örnek birkaç gönderi
        u_ali = User.query.filter_by(username="ali").first()
        u_veli = User.query.filter_by(username="veli").first()
        db.session.add_all([
            Post(user_id=u_ali.id, html_content="İlk gönderim!"),
            Post(user_id=u_veli.id, html_content="Merhaba Matties!"),
        ])
        db.session.commit()

# -------------------- BAŞLAT --------------------
if __name__ == "__main__":
    app.run(debug=True)
