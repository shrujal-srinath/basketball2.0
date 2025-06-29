from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///instance/games.db"
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs("instance", exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app)

# Game model
class Game(db.Model):
    code = db.Column(db.String(10), primary_key=True)
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    home_fouls = db.Column(db.Integer, default=0)
    away_fouls = db.Column(db.Integer, default=0)
    home_timeouts = db.Column(db.Integer, default=3)
    away_timeouts = db.Column(db.Integer, default=3)
    period = db.Column(db.Integer, default=1)
    home_name = db.Column(db.String(50), default="Home")
    away_name = db.Column(db.String(50), default="Away")
    game_clock = db.Column(db.String(5), default="10:00")
    shot_clock = db.Column(db.String(2), default="24")
    home_logo = db.Column(db.String(200), nullable=True)
    away_logo = db.Column(db.String(200), nullable=True)
    ended = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# Load game from DB
def get_game(code):
    return db.session.get(Game, code)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        code = request.form["game_code"].strip().upper()
        password = request.form["password"]
        home_name = request.form.get("home_name", "Home")
        away_name = request.form.get("away_name", "Away")

        if not code or get_game(code):
            return "Invalid or duplicate game code. <a href='/create'>Try again</a>"

        home_logo = request.files.get("home_logo")
        away_logo = request.files.get("away_logo")

        home_logo_path = None
        away_logo_path = None

        if home_logo:
            filename = secure_filename(home_logo.filename)
            relative_path = f"static/uploads/{code}_home_{filename}"
            full_path = os.path.join(app.root_path, relative_path)
            home_logo.save(full_path)
            home_logo_path = "/" + relative_path  # For use in <img src="...">

        if away_logo:
            filename = secure_filename(away_logo.filename)
            relative_path = f"static/uploads/{code}_away_{filename}"
            full_path = os.path.join(app.root_path, relative_path)
            away_logo.save(full_path)
            away_logo_path = "/" + relative_path  # For use in <img src="...">

        game = Game(
            code=code,
            home_name=home_name,
            away_name=away_name,
            home_logo=home_logo_path,
            away_logo=away_logo_path,
        )
        db.session.add(game)
        db.session.commit()

        session["game_code"] = code
        session["password"] = password
        return redirect(url_for("control", code=code))
    return render_template("create.html")

@app.route("/watch", methods=["GET", "POST"])
def watch():
    if request.method == "POST":
        code = request.form["game_code"].strip().upper()
        game = get_game(code)
        if not game:
            return render_template("watch.html", error="Invalid game code.")
        return redirect(url_for("display", code=code))
    return render_template("watch.html")

@app.route("/control/<code>", methods=["GET", "POST"])
def control(code):
    game = get_game(code)
    if not game:
        return "Game not found."

    if "password" not in session or session.get("game_code") != code:
        return redirect(url_for("home"))
    return render_template("control.html", game=game)

@app.route("/display/<code>")
def display(code):
    game = get_game(code)
    if not game:
        return "Game not found."
    return render_template("display.html", game=game)

@socketio.on("update")
def handle_update(data):
    code = data.get("code")
    updates = data.get("updates")
    game = get_game(code)
    if game:
        for key, value in updates.items():
            setattr(game, key, value)
        db.session.commit()
        emit("refresh", game.to_dict(), room=code)

@socketio.on("join")
def handle_join(code):
    join_room(code)
    game = get_game(code)
    if game:
        emit("refresh", game.to_dict(), room=code)

@socketio.on("buzzer")
def buzzer(code):
    emit("buzzer", room=code)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
