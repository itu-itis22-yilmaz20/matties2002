# app.py — Matties (tam sürüm)
# Port: 8080
# Admin hesapları: itu-itis22-yilmaz20 / yigit  (şifre: 1234)

import os, re, uuid
from flask import Flask, request, redirect, url_for, session, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# -------------------- AYARLAR --------------------
BASE_DIR = os.path.abspath(os.getcwd())
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "MATTIES_SECRET"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Birden fazla admin tanımı
ADMIN_USERNAMES = ["itu-itis22-yilmaz20", "yigit"]

# -------------------- MODELLER --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    html_content = db.Column(db.Text)

# -------------------- YARDIMCI --------------------
def current_user():
    u = session.get("user")
    return User.query.filter_by(username=u).first() if u else None

def save_media(f):
    n = secure_filename(f.filename)
    uid = f"{uuid.uuid4().hex[:6]}_{n}"
    f.save(os.path.join(UPLOAD_DIR, uid))
    return uid

def _delete_file_safely(path):
    try:
        if os.path.exists(path): os.remove(path)
    except: pass

# -------------------- HTML --------------------
INDEX_HTML = """
<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Matties</title>
<style>
body{font-family:Arial;background:#eef7ee;margin:0;}
header{background:#90ee90;padding:10px;display:flex;justify-content:space-between;}
.wrap{max-width:900px;margin:20px auto;background:#fff;padding:15px;border-radius:10px;}
a{text-decoration:none;color:#333;}
</style></head><body>
<header>
<strong>Matties</strong>
<div>
{% if me %}
<b>@{{me.username}}</b> |
<a href="/logout">Çıkış</a> |
<a href="/user/{{me.username}}">Profil</a> |
{% if me.username in admins %}<a href="/admin/users">Admin</a>{% endif %}
{% else %}
<a href="/login">Giriş Yap</a> | <a href="/register">Kayıt Ol</a>
{% endif %}
</div></header>

<div class="wrap">
{% if me %}
<h3>Gönderi paylaş</h3>
<form method="POST" action="/post" enctype="multipart/form-data">
<textarea name="text" style="width:100%;height:60px;" placeholder="Ne düşünüyorsun?"></textarea><br>
<input type="file" name="photo" accept="image/*,video/*,audio/*"><br>
<button>Paylaş</button>
</form>
{% endif %}
</div>

<div class="wrap">
<h3>Akış</h3>
{% for p,a in posts %}
<div style="border-bottom:1px solid #ddd;padding:8px 0;">
<a href="/user/{{a.username}}"><b>@{{a.username}}</b></a><br>
{{p.html_content|safe}}
</div>
{% endfor %}
</div></body></html>
"""

PROFILE_HTML = """
<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>{{u.username}} Profili</title></head>
<body style="font-family:Arial;background:#eef7ee;padding:30px;">
<h2>@{{u.username}}</h2>

{% if me and me.username == u.username %}
<form method="POST" action="/delete_account" onsubmit="return confirm('Hesabını silmek istiyor musun?');">
<button>Hesabımı Sil</button>
</form>
{% endif %}

{% if me and me.username in admins and u.username not in admins %}
<form method="POST" action="/admin/delete_user/{{u.username}}" onsubmit="return confirm('{{u.username}} silinsin mi?');">
<button>Bu kullanıcıyı sil (Admin)</button>
</form>
{% endif %}

<hr>
<h3>Gönderiler</h3>
{% for p in posts %}
<div style="background:white;margin:10px 0;padding:10px;border-radius:8px;">{{p.html_content|safe}}</div>
{% endfor %}
<p><a href="/">← Ana sayfa</a></p>
</body></html>
"""

ADMIN_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Admin</title></head>
<body style="font-family:Arial;background:#f5f5f5;padding:30px;">
<h2>Kullanıcılar</h2>
{% for u in users %}
<div>
<a href="/user/{{u.username}}">@{{u.username}}</a>
{% if u.username not in admins %}
<form method="POST" action="/admin/delete_user/{{u.username}}" style="display:inline;" onsubmit="return confirm('{{u.username}} silinsin mi?')">
<button>Sil</button></form>
{% else %}(Admin){% endif %}
</div>
{% endfor %}
<p><a href="/">Ana sayfa</a></p>
</body></html>
"""

LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Giriş</title></head>
<body style="font-family:Arial;background:#eef7ee;padding:40px;">
<h2>Giriş Yap</h2>
<form method="POST">
Kullanıcı: <input name="username"><br><br>
Şifre: <input type="password" name="password"><br><br>
<button>Giriş</button></form>
<a href="/">Ana sayfa</a>
</body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Kayıt</title></head>
<body style="font-family:Arial;background:#eef7ee;padding:40px;">
<h2>Kayıt Ol</h2>
<form method="POST">
Kullanıcı: <input name="username"><br><br>
Şifre: <input type="password" name="password"><br><br>
<button>Kayıt Ol</button></form>
<a href="/">Ana sayfa</a>
</body></html>
"""

# -------------------- ROUTELAR --------------------
@app.route("/")
def index():
    me = current_user()
    posts = Post.query.order_by(Post.id.desc()).all()
    data = [(p, User.query.get(p.user_id)) for p in posts]
    return render_template_string(INDEX_HTML, me=me, posts=data, admins=ADMIN_USERNAMES)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        u=request.form["username"].strip(); p=request.form["password"].strip()
        if User.query.filter_by(username=u).first(): return "Bu kullanıcı adı zaten var.",400
        db.session.add(User(username=u,password_hash=generate_password_hash(p)))
        db.session.commit(); session["user"]=u
        return redirect("/")
    return render_template_string(REGISTER_HTML)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["username"].strip(); p=request.form["password"].strip()
        user=User.query.filter_by(username=u).first()
        if not user or not check_password_hash(user.password_hash,p): return "Hatalı kullanıcı adı veya şifre.",401
        session["user"]=u; return redirect("/")
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))

@app.route("/post", methods=["POST"])
def post():
    me=current_user()
    if not me: return redirect("/login")
    text=request.form.get("text","").strip()
    photo=request.files.get("photo")
    html=text
    if photo and photo.filename:
        n=save_media(photo)
        ext=os.path.splitext(n)[1].lower()
        if ext in [".jpg",".png",".jpeg",".gif"]:
            html+=f"<br><img src='/uploads/{n}' style='max-width:100%;'>"
        elif ext in [".mp4",".webm"]:
            html+=f"<br><video controls src='/uploads/{n}' style='max-width:100%;'></video>"
        elif ext in [".mp3",".wav"]:
            html+=f"<br><audio controls src='/uploads/{n}'></audio>"
    db.session.add(Post(user_id=me.id,html_content=html)); db.session.commit()
    return redirect("/")

@app.route("/uploads/<filename>")
def serve_file(filename): return send_from_directory(UPLOAD_DIR, filename)

@app.route("/user/<username>")
def profile(username):
    me=current_user()
    u=User.query.filter_by(username=username).first()
    if not u: return "Kullanıcı yok.",404
    posts=Post.query.filter_by(user_id=u.id).order_by(Post.id.desc()).all()
    return render_template_string(PROFILE_HTML,u=u,me=me,admins=ADMIN_USERNAMES,posts=posts)

@app.route("/delete_account", methods=["POST"])
def delete_account():
    me=current_user()
    if not me: return redirect("/login")
    Post.query.filter_by(user_id=me.id).delete()
    db.session.delete(me); db.session.commit()
    session.pop("user", None)
    return "Hesap silindi. <a href='/'>Ana sayfa</a>"

@app.route("/admin/users")
def admin_users():
    if session.get("user") not in ADMIN_USERNAMES: return "Yetkisiz",403
    return render_template_string(ADMIN_HTML,users=User.query.all(),admins=ADMIN_USERNAMES)

@app.route("/admin/delete_user/<username>", methods=["POST"])
def admin_delete_user(username):
    if session.get("user") not in ADMIN_USERNAMES: return "Yetkisiz",403
    u=User.query.filter_by(username=username).first()
    if not u or u.username in ADMIN_USERNAMES: return "Admin silinemez",400
    Post.query.filter_by(user_id=u.id).delete()
    db.session.delete(u); db.session.commit()
    return redirect("/admin/users")

# -------------------- BAŞLAT --------------------
with app.app_context():
    db.create_all()
    for adm in ADMIN_USERNAMES:
        if not User.query.filter_by(username=adm).first():
            db.session.add(User(username=adm, password_hash=generate_password_hash("1234")))
    db.session.commit()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
