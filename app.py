# app.py — Matties (arkadaşlık sistemi + parlak yeşil tema)
import os, uuid, re, html
from typing import Union
from flask import Flask, request, redirect, url_for, session, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_
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

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a"}

# -------------------- MODELLER --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    privacy = db.Column(db.String(10), default="friends")

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    html_content = db.Column(db.Text)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)   # isteği gönderen
    friend_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False) # isteği alan
    status = db.Column(db.String(10), default="pending")  # pending / accepted
    __table_args__ = (db.UniqueConstraint('user_id','friend_id',name='_user_friend_uc'),)

# -------------------- YARDIMCI --------------------
def current_user():
    u = session.get("user")
    return User.query.filter_by(username=u).first() if u else None

def save_media(f):
    ext = os.path.splitext(f.filename)[1].lower()
    name = secure_filename(f"{uuid.uuid4().hex}{ext}")
    f.save(os.path.join(UPLOAD_DIR, name))
    return name

def embed_youtube_links(text:str)->str:
    yt = r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})"
    def rep(m): return f'<iframe width="420" height="236" src="https://www.youtube.com/embed/{m.group(1)}" frameborder="0" allowfullscreen></iframe>'
    safe = html.escape(text).replace("\n","<br>")
    safe = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank">\1</a>', safe)
    return re.sub(yt, rep, safe)

def are_friends(uid1:int, uid2:int)->bool:
    if not uid1 or not uid2: return False
    return Friendship.query.filter(
        or_(
            and_(Friendship.user_id==uid1, Friendship.friend_id==uid2, Friendship.status=="accepted"),
            and_(Friendship.user_id==uid2, Friendship.friend_id==uid1, Friendship.status=="accepted")
        )
    ).first() is not None

def friendship_status(me_id:int, target_id:int)->str:
    if not me_id: return "none"
    if me_id == target_id: return "self"
    if are_friends(me_id, target_id): return "friend"
    sent = Friendship.query.filter_by(user_id=me_id, friend_id=target_id, status="pending").first()
    if sent: return "sent"
    recv = Friendship.query.filter_by(user_id=target_id, friend_id=me_id, status="pending").first()
    if recv: return "received"
    return "none"

def can_view_posts(owner:User, viewer:Union[User,None])->bool:
    if owner.privacy=="public": return True
    if not viewer: return False
    if owner.id==viewer.id: return True
    return are_friends(owner.id, viewer.id)

# -------------------- HTML --------------------
INDEX_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Matties</title></head>
<body style="font-family:Arial;background:#00FF66;padding:20px;">
<h2>Matties</h2>
{% if me %}
<p>Hoş geldin, @{{me.username}}</p>
<a href="/logout">Çıkış</a> | <a href="/find_friend">Arkadaş Ara</a>
<form method="POST" action="/post" enctype="multipart/form-data" style="margin-top:10px;">
<textarea name="text" placeholder="Ne düşünüyorsun?" style="width:100%;height:60px;"></textarea><br>
<input type="file" name="media" accept="image/*,video/*,audio/*"><br>
<button>Paylaş</button></form>
{% else %}
<a href="/login">Giriş</a> | <a href="/register">Kayıt Ol</a>
{% endif %}
<hr>
{% for p,a in posts %}
<b>@{{a.username}}</b><br>{{p.html_content|safe}}<hr>
{% endfor %}
</body></html>
"""

PROFILE_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><title>{{u.username}}</title></head>
<body style="font-family:Arial;background:#00FF66;padding:40px;">
<h2>@{{u.username}}</h2>

{% if me %}
  {% if fs == 'self' %}
    <form method="POST" action="/delete_account" onsubmit="return confirm('Hesabını silmek istiyor musun?')">
      <button>Hesabımı Sil</button>
    </form>
  {% elif fs == 'friend' %}
    <form method="POST" action="/unfriend/{{u.username}}">
      <button>Arkadaşlıktan Çıkar</button>
    </form>
  {% elif fs == 'sent' %}
    <form method="POST" action="/cancel_request/{{u.username}}">
      <button>İsteği İptal Et</button>
    </form>
  {% elif fs == 'received' %}
    <form method="POST" action="/accept_request/{{u.username}}" style="display:inline;">
      <button>Kabul Et</button>
    </form>
    <form method="POST" action="/cancel_request/{{u.username}}" style="display:inline;">
      <button>Reddet</button>
    </form>
  {% else %}
    <form method="POST" action="/request_friend/{{u.username}}">
      <button>Arkadaş Ol</button>
    </form>
  {% endif %}

  {% if fs != 'self' %}
  <hr>
  <form method="POST" action="/delete_user/{{u.username}}" onsubmit="return confirm('Bu kullanıcıyı silmek istiyor musun?')">
    <button>Bu kullanıcıyı Sil</button>
  </form>
  {% endif %}
{% endif %}

<hr>
{% if can_view %}
  {% for p in posts %}
    <div style="background:white;padding:10px;margin:8px 0;border-radius:8px;">{{p.html_content|safe}}</div>
  {% endfor %}
{% else %}
  <p>Gönderilerini görmek için arkadaş olmanız gerekiyor.</p>
{% endif %}
<p><a href="/">← Ana sayfa</a></p>
</body></html>
"""

FIND_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>Arkadaş Ara</title></head>
<body style="font-family:Arial;background:#00FF66;padding:40px;">
<h2>Arkadaş Ara</h2>
<form method="GET" action="/find_friend">
  <input name="q" placeholder="Kullanıcı adı gir" value="{{query or ''}}">
  <button>Ara</button>
</form>
<hr>
{% if results %}
  {% for u in results %}
    <div><a href="/user/{{u.username}}">@{{u.username}}</a></div>
  {% endfor %}
{% elif query %}
  <p>Sonuç bulunamadı.</p>
{% endif %}
<p><a href="/">← Ana sayfa</a></p>
</body></html>
"""

# -------------------- ROUTELAR --------------------
@app.route("/")
def index():
    me=current_user()
    posts=[]
    for post in Post.query.order_by(Post.id.desc()).all():
        owner=User.query.get(post.user_id)
        if can_view_posts(owner,me): posts.append((post,owner))
    return render_template_string(INDEX_HTML, me=me, posts=posts)

@app.route("/find_friend")
def find_friend():
    me=current_user()
    q=(request.args.get("q") or "").strip().lower()
    results=[]
    if q: results=User.query.filter(User.username.ilike(f"%{q}%")).all()
    return render_template_string(FIND_HTML, query=q, results=results, me=me)

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        u=request.form["username"]; p=request.form["password"]
        if not u or not p: return "Boş olamaz"
        if User.query.filter_by(username=u).first(): return "Var zaten"
        db.session.add(User(username=u,password_hash=generate_password_hash(p)))
        db.session.commit(); session["user"]=u; return redirect("/")
    return '<form method=POST>Kullanıcı:<input name=username><br>Şifre:<input type=password name=password><br><button>Kayıt</button></form>'

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["username"]; p=request.form["password"]
        usr=User.query.filter_by(username=u).first()
        if not usr or not check_password_hash(usr.password_hash,p): return "Hatalı"
        session["user"]=u; return redirect("/")
    return '<form method=POST>Kullanıcı:<input name=username><br>Şifre:<input type=password name=password><br><button>Giriş</button></form>'

@app.route("/logout")
def logout():
    session.pop("user",None)
    return redirect("/")

@app.route("/post",methods=["POST"])
def post():
    me=current_user()
    if not me: return redirect("/login")
    text=request.form.get("text","")
    html_text=embed_youtube_links(text)
    f=request.files.get("media")
    if f and f.filename:
        n=save_media(f)
        ext=os.path.splitext(n)[1].lower()
        if ext in IMAGE_EXT: html_text+=f"<br><img src='/uploads/{n}' width=300>"
        elif ext in VIDEO_EXT: html_text+=f"<br><video controls width=400 src='/uploads/{n}'></video>"
        elif ext in AUDIO_EXT: html_text+=f"<br><audio controls src='/uploads/{n}'></audio>"
    db.session.add(Post(user_id=me.id,html_content=html_text)); db.session.commit()
    return redirect("/")

@app.route("/uploads/<fname>")
def uploads(fname): return send_from_directory(UPLOAD_DIR,fname)

@app.route("/user/<username>")
def profile(username):
    me=current_user()
    u=User.query.filter_by(username=username).first()
    if not u: return "Yok",404
    canv=can_view_posts(u,me)
    posts=Post.query.filter_by(user_id=u.id).order_by(Post.id.desc()).all() if canv else []
    fs = friendship_status(me.id, u.id) if me else "none"
    return render_template_string(PROFILE_HTML,u=u,me=me,posts=posts,can_view=canv,fs=fs)

# ---- Arkadaşlık işlemleri ----
@app.route("/request_friend/<username>", methods=["POST"])
def request_friend(username):
    me=current_user(); t=User.query.filter_by(username=username).first()
    if not me or not t or me.id==t.id: return redirect(url_for("profile",username=username))
    # varsa tekrar oluşturma
    if not Friendship.query.filter_by(user_id=me.id, friend_id=t.id).first() and \
       not Friendship.query.filter_by(user_id=t.id, friend_id=me.id).first():
        db.session.add(Friendship(user_id=me.id, friend_id=t.id, status="pending"))
        db.session.commit()
    return redirect(url_for("profile",username=username))

@app.route("/accept_request/<username>", methods=["POST"])
def accept_request(username):
    me=current_user(); t=User.query.filter_by(username=username).first()
    if not me or not t: return redirect(url_for("profile",username=username))
    req = Friendship.query.filter_by(user_id=t.id, friend_id=me.id, status="pending").first()
    if req:
        req.status = "accepted"
        db.session.commit()
    return redirect(url_for("profile",username=username))

@app.route("/cancel_request/<username>", methods=["POST"])
def cancel_request(username):
    me=current_user(); t=User.query.filter_by(username=username).first()
    if not me or not t: return redirect(url_for("profile",username=username))
    # hem benim gönderdiğim pending'i iptal et, hem bana gelen pending'i reddet
    Friendship.query.filter(
        or_(
            and_(Friendship.user_id==me.id, Friendship.friend_id==t.id, Friendship.status=="pending"),
            and_(Friendship.user_id==t.id, Friendship.friend_id==me.id, Friendship.status=="pending")
        )
    ).delete()
    db.session.commit()
    return redirect(url_for("profile",username=username))

@app.route("/unfriend/<username>", methods=["POST"])
def unfriend(username):
    me=current_user(); t=User.query.filter_by(username=username).first()
    if not me or not t: return redirect(url_for("profile",username=username))
    Friendship.query.filter(
        or_(
            and_(Friendship.user_id==me.id, Friendship.friend_id==t.id),
            and_(Friendship.user_id==t.id, Friendship.friend_id==me.id)
        )
    ).delete()
    db.session.commit()
    return redirect(url_for("profile",username=username))

# ---- Kullanıcı silme ----
@app.route("/delete_account",methods=["POST"])
def delete_acc():
    me=current_user()
    if me:
        Post.query.filter_by(user_id=me.id).delete()
        Friendship.query.filter(or_(Friendship.user_id==me.id, Friendship.friend_id==me.id)).delete()
        db.session.delete(me); db.session.commit()
        session.pop("user",None)
    return redirect("/")

@app.route("/delete_user/<username>",methods=["POST"])
def delete_user(username):
    target=User.query.filter_by(username=username).first()
    if target:
        Post.query.filter_by(user_id=target.id).delete()
        Friendship.query.filter(or_(Friendship.user_id==target.id, Friendship.friend_id==target.id)).delete()
        db.session.delete(target); db.session.commit()
    return redirect("/")

# -------------------- BAŞLAT --------------------
with app.app_context():
    db.create_all()
    for name in ["itu-itis22-yilmaz20","yigit"]:
        if not User.query.filter_by(username=name).first():
            db.session.add(User(username=name,password_hash=generate_password_hash("1234")))
    db.session.commit()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080,debug=True)
