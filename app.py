from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import uuid
import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///game.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
socketio = SocketIO(app)

# Safe upload folder creation
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# --------------------------- Database Model ---------------------------
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False)
    home_name = db.Column(db.String(50), default="Home")
    away_name = db.Column(db.String(50), default="Away")
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    home_fouls = db.Column(db.Integer, default=0)
    away_fouls = db.Column(db.Integer, default=0)
    home_timeouts = db.Column(db.Integer, default=0)
    away_timeouts = db.Column(db.Integer, default=0)
    period = db.Column(db.Integer, default=1)
    game_clock = db.Column(db.String(10), default="10:00")
    shot_clock = db.Column(db.String(10), default="24")
    home_logo = db.Column(db.String(100), nullable=True)
    away_logo = db.Column(db.String(100), nullable=True)

# --------------------------- Routes ---------------------------
@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['GET', 'POST'])
def create_game():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        password = request.form['password'].strip()
        if not code or not password:
            return "Missing code or password"
        if Game.query.filter_by(code=code).first():
            return "Game code already exists."
        new_game = Game(code=code)
        db.session.add(new_game)
        db.session.commit()
        session['game_code'] = code
        session['password'] = password
        return redirect(url_for('control', code=code))
    return render_template('create.html')

@app.route('/watch', methods=['GET', 'POST'])
def watch_game():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        if not Game.query.filter_by(code=code).first():
            return "Invalid game code."
        return redirect(url_for('display', code=code))
    return render_template('watch.html')

@app.route('/control/<code>', methods=['GET', 'POST'])
def control(code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return "Game not found."
    return render_template('control.html', game=game)

@app.route('/display/<code>')
def display(code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return "Game not found."
    return render_template('display.html', game=game)

@app.route('/upload_logo/<team>/<code>', methods=['POST'])
def upload_logo(team, code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return "Game not found."

    file = request.files['logo']
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        rel_path = os.path.relpath(filepath, 'static')

        if team == 'home':
            game.home_logo = rel_path
        else:
            game.away_logo = rel_path

        db.session.commit()
        socketio.emit('update', get_game_state(game), to=code)
        return redirect(url_for('control', code=code))
    return "No file uploaded."

# --------------------------- Helpers ---------------------------
def get_game_state(game):
    return {
        'home_name': game.home_name,
        'away_name': game.away_name,
        'home_score': game.home_score,
        'away_score': game.away_score,
        'home_fouls': game.home_fouls,
        'away_fouls': game.away_fouls,
        'home_timeouts': game.home_timeouts,
        'away_timeouts': game.away_timeouts,
        'period': game.period,
        'game_clock': game.game_clock,
        'shot_clock': game.shot_clock,
        'home_logo': game.home_logo,
        'away_logo': game.away_logo,
        'code': game.code
    }

# --------------------------- Socket Events ---------------------------
@socketio.on('join')
def on_join(data):
    join_room(data['code'])

@socketio.on('update')
def handle_update(data):
    game = Game.query.filter_by(code=data['code']).first()
    if not game:
        return
    for key, value in data.items():
        if hasattr(game, key) and key != 'code':
            setattr(game, key, value)
    db.session.commit()
    emit('update', get_game_state(game), to=game.code)

@socketio.on('buzzer')
def handle_buzzer(data):
    emit('buzzer', {'type': data['type']}, to=data['code'])

# --------------------------- Main ---------------------------
if __name__ == '__main__':
    socketio.run(app, debug=True)
