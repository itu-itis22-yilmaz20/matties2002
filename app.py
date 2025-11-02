# app.py — Flask mini sosyal ağ (Py3.9 uyumlu)
import os, uuid
from typing import Optional
from flask import (
    Flask, request, jsonify, render_template,
    send_from_directory, session, redirect, url_for, Response, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

# -------------------- FLASK APP --------------------
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "DEGISTIR_ILK_CALISTIRMADA")

# -------------------- VERİTABANI --------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------- SOCKET.IO --------------------
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# -------------------- YÜKLEME KLASÖRLERİ --------------------
BASE_DIR = os.path.abspath(os.getcwd())
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
MEDIA_DIR = os.path.join(UPLOAD_DIR, "media")

for d in [UPLOAD_DIR, AVATAR_DIR, MEDIA_DIR]:
    os.makedirs(d, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".ogg", ".m4v", ".mov"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}

def is_image(path): return os.path.splitext(path)[1].lower() in IMAGE_EXT
def is_video(path): return os.path.splitext(path)[1].lower() in VIDEO_EXT
def is_audio(path): return os.path.splitext(path)[1].lower() in AUDIO_EXT

# -------------------- MODELLER --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    bio = db.Column(db.String(500))
    avatar = db.Column(db.String(100))
    privacy = db.Column(db.String(10), default='friends')
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    comments = db.relationship('Comment', backref='commenter', lazy='dynamic')

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    html_content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    comments = db.relationship('Comment', backref='parent_post', lazy='dynamic')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    html_content = db.Column(db.Text, nullable=False)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(10), default='pending')
    __table_args__ = (db.UniqueConstraint('user_id', 'friend_id', name='_user_friend_uc'),)

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    html_content = db.Column(db.Text, nullable=False)

LIVE_STREAMS = {}

# -------------------- ADMIN AYARI --------------------
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "itu-itis22-yilmaz20")

# -------------------- YARDIMCI FONKSİYONLAR --------------------
def get_user_by_username(username): return User.query.filter_by(username=username).first()
def get_user_by_id(uid): return db.session.get(User, uid)
def is_admin(): return session.get("user") == ADMIN_USERNAME

def delete_user_and_related(user: User):
    """Kullanıcıyı ve tüm ilişkili verilerini siler."""
    Comment.query.filter_by(user_id=user.id).delete()
    Post.query.filter_by(user_id=user.id).delete()
    Friendship.query.filter(
        or_(Friendship.user_id == user.id, Friendship.friend_id == user.id)
    ).delete()
    DirectMessage.query.filter(
        or_(DirectMessage.from_user_id == user.id, DirectMessage.to_user_id == user.id)
    ).delete()
    if user.avatar:
        try: os.remove(os.path.join(AVATAR_DIR, user.avatar))
        except OSError: pass
    db.session.delete(user)
    db.session.commit()

# -------------------- ROTALAR --------------------
@app.route("/")
def index():
    return render_template("index.html") if os.path.exists("templates/index.html") else "Hello!"

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if not u or not p: return "Eksik bilgi", 400
        if get_user_by_username(u): return "Bu kullanıcı adı var.", 400
        db.session.add(User(username=u, password_hash=generate_password_hash(p)))
        db.session.commit()
        session["user"] = u
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        user = get_user_by_username(u)
        if not user or not check_password_hash(user.password_hash, p):
            return "Hatalı giriş.", 401
        session["user"] = u
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))

# -------------------- KULLANICI SİLME --------------------
@app.route("/admin/delete_user/<username>", methods=["POST"])
def admin_delete_user(username):
    if not is_admin():
        return "Yetkin yok.", 403
    target = get_user_by_username(username)
    if not target:
        return "Kullanıcı bulunamadı.", 404
    if target.username == ADMIN_USERNAME:
        return "Kendini silemezsin.", 400

    delete_user_and_related(target)
    return f"{username} adlı kullanıcı tamamen silindi.", 200

# -------------------- SUNUCU --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
