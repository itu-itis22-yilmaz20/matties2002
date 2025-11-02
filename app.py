# app.py — Flask mini sosyal ağ (Py3.9 uyumlu)
import os
from flask_socketio import SocketIO
from typing import Optional
from flask import (
    Flask, request, jsonify, render_template, # DEĞİŞTİ: render_template_string yerine render_template
    send_from_directory, session, redirect, url_for, Response, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room, send

# YENİ EKLENTİLER: Veritabanı için
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

# -------------------- FLASK APP (route'lardan ÖNCE!) --------------------
# Yeni: template_folder ve static_folder ayarları standart kullanıma ayarlandı
app = Flask(__name__) 
app.secret_key = os.environ.get("APP_SECRET", "DEGISTIR_ILK_CALISTIRMADA")

# YENİ: SQLite veritabanı yapılandırması
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)  # SQLAlchemy nesnesi oluştur

# SocketIO'yu başlat
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------- YÜKLEME KLASÖRLERİ & LİMİTLER --------------------
BASE_DIR = os.path.abspath(os.getcwd())
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
MEDIA_DIR = os.path.join(UPLOAD_DIR, "media")  # video & ses

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# Maksimum yükleme boyutu (örn. 200 MB)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".ogg", ".m4v", ".mov"}  # MP4 dahil
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}


def is_image(path): return os.path.splitext(path)[1].lower() in IMAGE_EXT


def is_video(path): return os.path.splitext(path)[1].lower() in VIDEO_EXT


def is_audio(path): return os.path.splitext(path)[1].lower() in AUDIO_EXT


# -------------------- VERİ YAPILARI (SQLAlchemy Modelleri) --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    bio = db.Column(db.String(500))
    avatar = db.Column(db.String(100))
    privacy = db.Column(db.String(10), default='friends')  # 'friends' veya 'public'
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    comments = db.relationship('Comment', backref='commenter', lazy='dynamic')
    def __repr__(self): return f'<User {self.username}>'
    def get_avatar_path(self):
        return f"/avatar/{self.avatar}" if self.avatar else None

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    html_content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='parent_post', lazy='dynamic')
    def to_dict(self):
        return {
            'id': self.id,
            'user': self.author.username,
            'html': self.html_content,
            'likes': self.likes
        }

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    html_content = db.Column(db.Text, nullable=False)
    def to_dict(self):
        return {"user": self.commenter.username, "html": self.html_content}

class Friendship(db.Model):
    __tablename__ = 'friendship'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)  # İsteği gönderen/arkadaş
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)  # İsteği alan/arkadaş
    status = db.Column(db.String(10), default='pending')  # 'pending' (bekliyor) veya 'accepted' (kabul)
    __table_args__ = (db.UniqueConstraint('user_id', 'friend_id', name='_user_friend_uc'),)

class DirectMessage(db.Model):
    __tablename__ = 'direct_message'
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    html_content = db.Column(db.Text, nullable=False)
    sender = db.relationship('User', foreign_keys=[from_user_id], backref='sent_dms')
    recipient = db.relationship('User', foreign_keys=[to_user_id], backref='received_dms')

LIVE_STREAMS = {}  # {"username": "socketio_room_id"}


# -------------------- YARDIMCI VERİTABANI FONKSİYONLARI --------------------
def get_user_by_username(username: Optional[str]) -> Optional[User]:
    if not username: return None
    return User.query.filter_by(username=username).first()

def get_user_by_id(user_id: Optional[int]) -> Optional[User]:
    if not user_id: return None
    return db.session.get(User, user_id)

def get_user_id_by_username(username: Optional[str]) -> Optional[int]:
    user = get_user_by_username(username)
    return user.id if user else None

def get_username_by_id(user_id: Optional[int]) -> Optional[str]:
    user = get_user_by_id(user_id)
    return user.username if user else None

def get_friendship_status(user_id, target_id):
    if user_id == target_id: return 'self'
    is_friend = Friendship.query.filter(
        or_(
            (Friendship.user_id == user_id) & (Friendship.friend_id == target_id) & (Friendship.status == 'accepted'),
            (Friendship.user_id == target_id) & (Friendship.friend_id == user_id) & (Friendship.status == 'accepted')
        )
    ).first()
    if is_friend: return 'friend'
    sent_req = Friendship.query.filter_by(user_id=user_id, friend_id=target_id, status='pending').first()
    if sent_req: return 'sent'
    recv_req = Friendship.query.filter_by(user_id=target_id, friend_id=user_id, status='pending').first()
    if recv_req: return 'received'
    return 'none'

def can_view_posts(owner_id: int, viewer_id: Optional[int]) -> bool:
    owner = get_user_by_id(owner_id)
    if not owner: return False
    privacy = owner.privacy
    if privacy == "public": return True
    if viewer_id is None: return False
    if viewer_id == owner_id: return True
    return get_friendship_status(viewer_id, owner_id) == 'friend'


# -------------------- Range (Partial Content) Sunucu (Aynı kaldı) --------------------
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
        start = max(0, start);
        end = min(end, file_size - 1)
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

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length)
    }
    return Response(generate(), 206, mimetype=mimetype, headers=headers)


# -------------------- ANA SAYFA (gizlilik filtreli) --------------------
@app.route("/")
def index():
    me_username = session.get("user")
    current_user = get_user_by_username(me_username)
    me_id = current_user.id if current_user else None

    all_posts = Post.query.order_by(Post.id.desc()).all()
    visible_posts = [p for p in all_posts if can_view_posts(p.user_id, me_id)]

    friends_of_current = set()
    req_sent_of_current = set()
    req_recv_of_current = set()

    if current_user:
        friends_q = Friendship.query.filter(
            or_(Friendship.user_id == me_id, Friendship.friend_id == me_id),
            Friendship.status == 'accepted'
        ).all()
        for f in friends_q:
            friend_id = f.friend_id if f.user_id == me_id else f.user_id
            friends_of_current.add(get_username_by_id(friend_id))

        sent_q = Friendship.query.filter_by(user_id=me_id, status='pending').all()
        req_sent_of_current = {get_username_by_id(f.friend_id) for f in sent_q}

        recv_q = Friendship.query.filter_by(friend_id=me_id, status='pending').all()
        req_recv_of_current = {get_username_by_id(f.user_id) for f in recv_q}

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template(
        "index.html", # Yeni şablon dosyası
        posts=visible_posts,
        LIVE_STREAMS=LIVE_STREAMS,
        current_user=current_user,
        friends_of_current=friends_of_current,
        req_sent_of_current=req_sent_of_current,
        req_recv_of_current=req_recv_of_current,
    )


# -------------------- KAYIT & GİRİŞ --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        bio = (request.form.get("bio") or "").strip()
        priv = (request.form.get("privacy") or "friends").strip().lower()
        if priv not in {"friends", "public"}: priv = "friends"
        if not username or not password:
            return "Kullanıcı adı ve şifre gerekli. <a href='/register'>&larr; Geri</a>", 400

        if User.query.filter_by(username=username).first():
            return "Bu kullanıcı adı alınmış. <a href='/register'>&larr; Geri</a>", 400

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            bio=bio,
            avatar=None,
            privacy=priv
        )
        db.session.add(new_user)
        db.session.commit()

        session["user"] = username
        return redirect(url_for("index"))
    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        u = User.query.filter_by(username=username).first()
        if not u or not check_password_hash(u.password_hash, password):
            return "Geçersiz kimlik. <a href='/login'>&larr; Geri</a>", 401

        session["user"] = username
        return redirect(url_for("index"))
    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))


# -------------------- PROFİL & AVATAR --------------------
@app.route("/user/<username>", methods=["GET", "POST"])
def profile(username):
    user = get_user_by_username(username)
    if not user: return "Kullanıcı bulunamadı.", 404

    me_username = session.get("user")
    current_user = get_user_by_username(me_username)
    me_id = current_user.id if current_user else None

    if request.method == "POST":
        action = request.form.get("action")
        if action == "avatar":
            if not current_user or current_user.username != username:
                return "Yetkisiz işlem.", 403
            file = request.files.get("avatar")
            if not file or not file.filename:
                return redirect(url_for("profile", username=username))
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in IMAGE_EXT:
                return "Sadece resim dosyası yükleyin.", 400
            safe = secure_filename(file.filename)
            stem, _ = os.path.splitext(safe)
            unique = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
            file.save(os.path.join(AVATAR_DIR, unique))

            old = user.avatar
            if old and old != unique:
                try:
                    os.remove(os.path.join(AVATAR_DIR, old))
                except OSError:
                    pass

            user.avatar = unique
            db.session.commit()
            return redirect(url_for("profile", username=username))

        elif action == "privacy":
            if not current_user or current_user.username != username:
                return "Yetkisiz işlem.", 403
            priv = (request.form.get("privacy") or "friends").strip().lower()
            if priv in {"friends", "public"}:
                user.privacy = priv
                db.session.commit()
            return redirect(url_for("profile", username=username))

    user_posts = user.posts.order_by(Post.id.desc()).all()
    status = get_friendship_status(me_id, user.id) if current_user else 'none'

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template(
        "profile.html", # Yeni şablon dosyası
        user=user,
        current_user=current_user,
        user_posts=user_posts,
        status=status,
        can_view=can_view_posts(user.id, me_id),
        LIVE_STREAMS=LIVE_STREAMS
    )


@app.route("/avatar/<filename>")
def serve_avatar(filename):
    return send_from_directory(AVATAR_DIR, filename)


# -------------------- GÖNDERİLER (POST) (Aynı kaldı) --------------------
def save_media(file_storage, target_dir):
    safe = secure_filename(file_storage.filename)
    stem, ext = os.path.splitext(safe)
    unique = f"{stem}_{uuid.uuid4().hex[:8]}{ext.lower()}"
    file_storage.save(os.path.join(target_dir, unique))
    return unique


@app.route("/post", methods=["POST"])
def post():
    if "user" not in session: return "Giriş yapmanız gerekiyor.", 401
    current_user = get_user_by_username(session["user"])
    if not current_user: return "Kullanıcı bulunamadı.", 404

    text = (request.form.get("text") or "").strip()
    photo = request.files.get("photo")
    media = request.files.get("media")

    parts = []
    if text:
        parts.append(text.replace("\n", "<br>"))

    if photo and photo.filename:
        if not is_image(photo.filename): return "Sadece resim yükleyin (jpg, png, webp...).", 400
        img_name = save_media(photo, UPLOAD_DIR)
        parts.append(f"<img class='media' src='/uploads/{img_name}' alt=''>")

    if media and media.filename:
        ext = os.path.splitext(media.filename)[1].lower()
        if ext not in VIDEO_EXT.union(AUDIO_EXT): return "Desteklenmeyen medya biçimi.", 400
        media_name = save_media(media, MEDIA_DIR)
        if ext in VIDEO_EXT:
            parts.append(f"<video controls preload='metadata' src='/media/{media_name}'></video>")
        else:
            parts.append(f"<audio controls src='/media/{media_name}'></audio>")

    if not parts: return "Boş gönderi olmaz.", 400

    new_post = Post(user_id=current_user.id, html_content="<br>".join(parts), likes=0)
    db.session.add(new_post)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/like/<int:post_id>", methods=["POST"])
def like_post(post_id):
    me = session.get("user")
    current_user = get_user_by_username(me)
    me_id = current_user.id if current_user else None

    post = db.session.get(Post, post_id)
    if post and can_view_posts(post.user_id, me_id):
        post.likes += 1
        db.session.commit()

    return redirect(request.referrer or url_for("index"))


# -------------------- YORUMLAR (Aynı kaldı) --------------------
@app.route("/comment/<int:post_id>", methods=["POST"])
def add_comment(post_id):
    if "user" not in session: return redirect(url_for("login"))
    current_user = get_user_by_username(session["user"])
    if not current_user: return redirect(url_for("login"))

    target_post = db.session.get(Post, post_id)
    if not target_post: return "Gönderi bulunamadı.", 404
    if not can_view_posts(target_post.user_id, current_user.id): return "İzniniz yok.", 403

    text = (request.form.get("text") or "").strip()
    media = request.files.get("media")

    parts = []
    if text: parts.append(text.replace("\n", "<br>"))
    if media and media.filename:
        ext = os.path.splitext(media.filename)[1].lower()
        if ext in IMAGE_EXT:
            name = save_media(media, UPLOAD_DIR)
            parts.append(f"<img class='media' src='/uploads/{name}' alt=''>")
        elif ext in VIDEO_EXT:
            name = save_media(media, MEDIA_DIR)
            parts.append(f"<video controls preload='metadata' src='/media/{name}'></video>")
        elif ext in AUDIO_EXT:
            name = save_media(media, MEDIA_DIR)
            parts.append(f"<audio controls src='/media/{name}'></audio>")
        else:
            return "Desteklenmeyen medya tipi.", 400

    if not parts: return redirect(request.referrer or url_for("index"))

    new_comment = Comment(post_id=post_id, user_id=current_user.id, html_content="<br>".join(parts))
    db.session.add(new_comment)
    db.session.commit()
    return redirect(request.referrer or url_for("index"))


# -------------------- ARKADAŞLIK (Aynı kaldı) --------------------

@app.route("/request_friend/<username>", methods=["POST"])
def request_friend(username):
    me = get_user_by_username(session.get("user"))
    target = get_user_by_username(username)
    if not me or not target: return redirect(url_for("login"))
    if me.id == target.id: return redirect(url_for("profile", username=me.username))

    status = get_friendship_status(me.id, target.id)

    if status == 'friend' or status == 'sent':
        return redirect(request.referrer or url_for("profile", username=username))

    if status == 'received':
        req = Friendship.query.filter_by(user_id=target.id, friend_id=me.id, status='pending').first()
        if req:
            req.status = 'accepted'
            db.session.commit()
            return redirect(request.referrer or url_for("profile", username=username))

    new_req = Friendship(user_id=me.id, friend_id=target.id, status='pending')
    db.session.add(new_req)
    db.session.commit()
    return redirect(request.referrer or url_for("profile", username=username))


@app.route("/cancel_request/<username>", methods=["POST"])
def cancel_request(username):
    me = get_user_by_username(session.get("user"))
    target = get_user_by_username(username)
    if not me or not target: return redirect(url_for("login"))

    req = Friendship.query.filter_by(user_id=me.id, friend_id=target.id, status='pending').first()
    if req:
        db.session.delete(req)
        db.session.commit()

    return redirect(request.referrer or url_for("profile", username=username))


@app.route("/accept_request/<username>", methods=["POST"])
def accept_request(username):
    me = get_user_by_username(session.get("user"))
    target = get_user_by_username(username)
    if not me or not target: return redirect(url_for("login"))

    req = Friendship.query.filter_by(user_id=target.id, friend_id=me.id, status='pending').first()
    if req:
        req.status = 'accepted'
        db.session.commit()

    return redirect(request.referrer or url_for("profile", username=username))


@app.route("/decline_request/<username>", methods=["POST"])
def decline_request(username):
    me = get_user_by_username(session.get("user"))
    target = get_user_by_username(username)
    if not me or not target: return redirect(url_for("login"))

    req = Friendship.query.filter_by(user_id=target.id, friend_id=me.id, status='pending').first()
    if req:
        db.session.delete(req)
        db.session.commit()

    return redirect(request.referrer or url_for("profile", username=username))


@app.route("/requests")
def requests_box():
    me = get_user_by_username(session.get("user"))
    if not me: return redirect(url_for("login"))
    me_id = me.id

    incoming_reqs = Friendship.query.filter_by(friend_id=me_id, status='pending').all()
    incoming = sorted([get_username_by_id(r.user_id) for r in incoming_reqs])

    outgoing_reqs = Friendship.query.filter_by(user_id=me_id, status='pending').all()
    outgoing = sorted([get_username_by_id(r.friend_id) for r in outgoing_reqs])

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("requests.html", incoming=incoming, outgoing=outgoing)


# -------------------- DM (Aynı kaldı) --------------------
@app.route("/inbox")
def inbox():
    me = get_user_by_username(session.get("user"))
    if not me: return redirect(url_for("login"))
    me_id = me.id

    dms = DirectMessage.query.filter(or_(DirectMessage.from_user_id == me_id, DirectMessage.to_user_id == me_id)).all()

    users = set()
    for m in dms:
        if m.from_user_id != me_id:
            users.add(m.sender.username)
        if m.to_user_id != me_id:
            users.add(m.recipient.username)

    sorted_users = sorted(list(users))

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("inbox.html", sorted_users=sorted_users)


@app.route("/dm/<username>", methods=["GET", "POST"])
def dm(username):
    me = get_user_by_username(session.get("user"))
    target = get_user_by_username(username)
    if not me or not target: return redirect(url_for("login"))

    if request.method == "POST":
        msg = (request.form.get("text") or "").strip()
        media = request.files.get("media")
        parts = []

        if msg: parts.append(msg.replace("\n", "<br>"))
        if media and media.filename:
            ext = os.path.splitext(media.filename)[1].lower()
            if ext in IMAGE_EXT:
                name = save_media(media, UPLOAD_DIR)
                parts.append(f"<img class='media' src='/uploads/{name}' alt=''>")
            elif ext in VIDEO_EXT:
                name = save_media(media, MEDIA_DIR)
                parts.append(f"<video controls preload='metadata' src='/media/{name}'></video>")
            elif ext in AUDIO_EXT:
                name = save_media(media, MEDIA_DIR)
                parts.append(f"<audio controls src='/media/{name}'></audio>")
            else:
                return "Desteklenmeyen medya tipi.", 400

        if parts:
            new_dm = DirectMessage(from_user_id=me.id, to_user_id=target.id, html_content="<br>".join(parts))
            db.session.add(new_dm)
            db.session.commit()

        return redirect(url_for("dm", username=username))

    conv = DirectMessage.query.filter(
        or_(
            (DirectMessage.from_user_id == me.id) & (DirectMessage.to_user_id == target.id),
            (DirectMessage.from_user_id == target.id) & (DirectMessage.to_user_id == me.id)
        )
    ).order_by(DirectMessage.id).all()

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("dm.html", target_user=target, conversation=conv, me_id=me.id)


# -------------------- DOSYA SERVİSİ (Aynı kaldı) --------------------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/media/<path:filename>")
def serve_media(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXT:
        mimetype = "video/mp4" if ext in {".mp4", ".m4v"} else ("video/webm" if ext == ".webm" else "video/ogg")
    elif ext in AUDIO_EXT:
        if ext == ".mp3":
            mimetype = "audio/mpeg"
        elif ext == ".wav":
            mimetype = "audio/wav"
        elif ext == ".m4a":
            mimetype = "audio/mp4"
        else:
            mimetype = "audio/ogg"
    else:
        mimetype = "application/octet-stream"
    return partial_response(os.path.join(MEDIA_DIR, filename), mimetype)


# -------------------- ARAMA (Aynı kaldı) --------------------
@app.route("/search")
def search():
    me_user = get_user_by_username(session.get("user"))
    me_id = me_user.id if me_user else None
    q = (request.args.get("q") or "").strip().lower()
    if not q: return redirect(url_for("index"))

    results_q = Post.query.join(User).filter(
        or_(
            Post.html_content.ilike(f'%{q}%'),
            User.username.ilike(f'%{q}%')
        )
    ).order_by(Post.id.desc()).all()

    results = [p for p in results_q if can_view_posts(p.user_id, me_id)]

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("search.html", query=q, results=results)


@app.route("/find_friend")
def find_friend():
    q = (request.args.get("name") or "").strip().lower()
    if not q: return redirect(url_for("index"))

    me_user = get_user_by_username(session.get("user"))
    me_id = me_user.id if me_user else None

    matches = User.query.filter(User.username.ilike(f'%{q}%')).all()

    # DEĞİŞTİ: render_template_string yerine render_template kullanıldı
    return render_template("find_friend.html", query=q, matches=matches, me_user=me_user, me_id=me_id, get_friendship_status=get_friendship_status)


# -------------------- CANLI YAYIN (WEBRTC Sinyalleşme) --------------------

@app.route("/go_live")
def go_live_page():
    me = session.get("user")
    if not me: return redirect(url_for('login'))
    # DEĞİŞTİ: LIVE_STREAM_PAGE_TEMPLATE yerine render_template kullanıldı
    return render_template("live_stream.html", streamer_user=me, LIVE_STREAMS=LIVE_STREAMS)


@app.route("/live_stream/<string:username>")
def live_stream_page(username):
    if username not in LIVE_STREAMS:
        return redirect(url_for('index'))
    # DEĞİŞTİ: LIVE_VIEWER_PAGE_TEMPLATE yerine render_template kullanıldı
    return render_template("live_viewer.html", streamer_user=username, viewer_user=session.get("user"))


# SocketIO Olay Yöneticileri (Aynı kaldı)
@socketio.on('join_live_room')
def handle_join_live_room(data):
    username = data.get('username')
    streamer = data.get('streamer')
    me = session.get("user")

    if get_user_by_username(streamer):
        room_id = f"live_{streamer}"
        join_room(room_id)
        print(f"User {username} joined live room {room_id} (SID: {request.sid})")

        if username == streamer:
            LIVE_STREAMS[streamer] = room_id
            print(f"Streamer {streamer} is now active.")
        elif streamer in LIVE_STREAMS:
            emit('new_viewer', {'viewer_id': request.sid, 'viewer_user': me}, room=f"live_{streamer}",
                 include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    disconnected_user = None
    for user, room in LIVE_STREAMS.items():
        if room == f"live_{user}":
            disconnected_user = user
            break

    if disconnected_user:
        LIVE_STREAMS.pop(disconnected_user, None)
        room_id = f"live_{disconnected_user}"
        emit('stream_status', {'status': 'stopped'}, room=room_id, broadcast=True)
        print(f"Streamer {disconnected_user} disconnected. Live stream stopped.")
    else:
        for streamer in LIVE_STREAMS.keys():
            emit('viewer_left', {'viewer_id': request.sid}, room=f"live_{streamer}")


@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    target_sid = data.get('target_sid')  # Hedef SocketID (izleyici/yayıncı)
    signal_data = data.get('signal')

    if target_sid:
        emit('webrtc_signal', {'signal': signal_data, 'sender_sid': request.sid}, room=target_sid)


# -------------------- API (SQLAlchemy'ye Uyarlandı ve Düzeltildi) (Aynı kaldı) --------------------
@app.route("/api/posts")
def api_posts():
    me_user = get_user_by_username(session.get("user"))
    me_id = me_user.id if me_user else None

    all_posts = Post.query.order_by(Post.id.desc()).all()
    visible_posts = [p.to_dict() for p in all_posts if can_view_posts(p.user_id, me_id)]
    return jsonify(visible_posts)


@app.route("/api/users")
def api_users():
    users = User.query.with_entities(User.username).all()
    return jsonify([u[0] for u in users])


@app.route("/api/comments/<int:post_id>")
def api_comments(post_id):
    me_user = get_user_by_username(session.get("user"))
    me_id = me_user.id if me_user else None

    target_post = db.session.get(Post, post_id)
    if not target_post: return jsonify([])

    if not can_view_posts(target_post.user_id, me_id):
        return jsonify([])

    comments = [c.to_dict() for c in target_post.comments.all()]
    return jsonify(comments)


# -------------------- ÇALIŞTIR & VERİTABANI BAŞLATMA (Aynı kaldı) --------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)

    with app.app_context():
        db.create_all()

    print(f"Çalışıyor: http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
