# app.py — Admin kullanıcı silme + medya temizleme (Flask 3 uyumlu)
# Çalıştırma:
# python -m venv venv
# source venv/bin/activate
# pip install flask sqlalchemy flask_sqlalchemy werkzeug
# export ADMIN_USERNAME="itu-itis22-yilmaz20"   # isteğe bağlı
# python app.py

import os
import re
import uuid
from flask import Flask, request, redirect, url_for, session, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_
from werkzeug.security import generate_password_hash

# -------------------- AYARLAR --------------------
BASE_DIR = os.path.abspath(os.getcwd())
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
MEDIA_DIR  = os.path.join(UPLOAD_DIR, "media")
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "CHANGE_THIS_SECRET")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "itu-itis22-yilmaz20")

# -------------------- MODELLER --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(120))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    html_content = db.Column(db.Text)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    html_content = db.Column(db.Text)

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    to_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    html_content = db.Column(db.Text)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
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
    # örn: src="/uploads/xyz.png" veya src='/media/abc.mp4'
    for rel in re.findall(r'src=[\'"](/(?:uploads|media)/[^\'"]+)[\'"]', html):
        rel_norm = os.path.normpath(rel).lstrip("/")  # -> uploads/xyz.png
        full = os.path.join(BASE_DIR, rel_norm)
        # ekstra güvenlik: sadece uploads veya media altındaki dosyaları sil
        if os.path.commonpath([full, os.path.join(BASE_DIR, "uploads")]) == os.path.join(BASE_DIR, "uploads") \
           or os.path.commonpath([full, os.path.join(BASE_DIR, "media")]) == os.path.join(BASE_DIR, "media"):
            paths.append(full)
    return paths

# -------------------- SAYFALAR (HTML tek dosyada) --------------------
INDEX_HTML = """
<!doctype html>
<title>Admin Panel (Basit)</title>
<h3>Admin test / hızlı linkler</h3>
<ul>
  <li><a href="/login/{{ admin }}">Admin olarak giriş yap</a></li>
  <li><a href="/admin/users">Admin - Kullanıcılar</a></li>
</ul>
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
    <p class="small">Giriş yapan: {{ current_user or '(yok)' }} — <a href="/logout">Çıkış</a></p>
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

@app.route("/")
def index():
    return render_template_string(INDEX_HTML, admin=ADMIN_USERNAME)

@app.route("/login/<username>")
def fake_login(username):
    # Basit test login (gerçek projede normal auth kullan)
    session["user"] = username
    return f"Giriş yapıldı: {username}. <a href='/admin/users'>Admin Paneli</a>"

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))

# -------------------- ADMIN PANELİ --------------------
@app.route("/admin/users")
def admin_users():
    if session.get("user") != ADMIN_USERNAME:
        return "Yetkisiz erişim.", 403
    users = User.query.order_by(User.username).all()
    return render_template_string(ADMIN_HTML, users=users, admin_name=ADMIN_USERNAME, current_user=session.get("user"))

@app.route("/admin/delete_user/<username>", methods=["POST"])
def admin_delete_user(username):
    if session.get("user") != ADMIN_USERNAME:
        return "Yetkisiz erişim.", 403

    target = User.query.filter_by(username=username).first()
    if not target:
        return "Kullanıcı bulunamadı.", 404
    if target.username == ADMIN_USERNAME:
        return "Admin kullanıcısını silemezsin.", 400

    # 1) Avatar dosyası (uploads/avatars/...)
    if target.avatar:
        _delete_file_safely(os.path.join(AVATAR_DIR, target.avatar))

    # 2) Post medya dosyalarını temizle
    for p in Post.query.filter_by(user_id=target.id).all():
        for fp in _collect_media_paths_from_html(p.html_content):
            _delete_file_safely(fp)

    # 3) Yorum medya dosyalarını temizle
    for c in Comment.query.filter_by(user_id=target.id).all():
        for fp in _collect_media_paths_from_html(c.html_content):
            _delete_file_safely(fp)

    # 4) DM medya dosyalarını temizle (gönderdiği ve aldığı)
    dms = DirectMessage.query.filter(
        or_(DirectMessage.from_user_id == target.id, DirectMessage.to_user_id == target.id)
    ).all()
    for m in dms:
        for fp in _collect_media_paths_from_html(m.html_content):
            _delete_file_safely(fp)

    # 5) Veritabanı kayıtlarını sil (ilişkili tablolar)
    Friendship.query.filter(
        or_(Friendship.user_id == target.id, Friendship.friend_id == target.id)
    ).delete(synchronize_session=False)

    Comment.query.filter_by(user_id=target.id).delete(synchronize_session=False)
    DirectMessage.query.filter(
        or_(DirectMessage.from_user_id == target.id, DirectMessage.to_user_id == target.id)
    ).delete(synchronize_session=False)
    Post.query.filter_by(user_id=target.id).delete(synchronize_session=False)

    # 6) Kullanıcıyı sil
    db.session.delete(target)
    db.session.commit()
    return redirect(url_for("admin_users"))

# -------------------- DB OLUŞTURMA ve ÖRNEK KULLANICILAR --------------------
with app.app_context():
    db.create_all()
    # örnek kullanıcı ekleme (password_hash alanı zorunlu olduğu için hash veriyoruz)
    if not User.query.first():
        pwd = generate_password_hash("1234")
        db.session.add_all([
            User(username=ADMIN_USERNAME, password_hash=pwd, avatar=None),
            User(username="ali", password_hash=pwd, avatar=None),
            User(username="veli", password_hash=pwd, avatar=None),
            User(username="ayse", password_hash=pwd, avatar=None),
        ])
        db.session.commit()

# -------------------- BAŞLAT --------------------
if __name__ == "__main__":
    app.run(debug=True)
