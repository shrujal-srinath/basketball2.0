from flask import Flask, render_template, request, redirect, session, url_for, send_file
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from threading import Timer
from werkzeug.utils import secure_filename
import os
import socket
import csv
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key'
socketio = SocketIO(app, async_mode='eventlet')

# ✅ SQLite Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///games.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/logos'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)

# ✅ Game Model
class Game(db.Model):
    code = db.Column(db.String(10), primary_key=True)
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    home_fouls = db.Column(db.Integer, default=0)
    away_fouls = db.Column(db.Integer, default=0)
    period = db.Column(db.Integer, default=1)
    home_name = db.Column(db.String(50), default='Home')
    away_name = db.Column(db.String(50), default='Away')
    game_clock = db.Column(db.String(10), default='10:00')
    shot_clock = db.Column(db.Integer, default=24)
    home_logo = db.Column(db.String(100), default='')
    away_logo = db.Column(db.String(100), default='')
    ended = db.Column(db.Boolean, default=False)

# ✅ Utility to fetch game
def get_game(code):
    return Game.query.get(code)

# ✅ Timers
timers = {}

# ✅ Clock Countdown Logic
def tick(code):
    game = get_game(code)
    if not game:
        return

    if game.game_clock != "00:00":
        minutes, seconds = map(int, game.game_clock.split(":"))
        total_seconds = minutes * 60 + seconds - 1
        total_seconds = max(0, total_seconds)
        game.game_clock = f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    if game.shot_clock > 0:
        game.shot_clock -= 1

    db.session.commit()
    socketio.emit('game_updated', {
        'code': code,
        'updates': {
            'game_clock': game.game_clock,
            'shot_clock': game.shot_clock
        }
    }, to=code)

    if game.game_clock != "00:00" or game.shot_clock > 0:
        timers[code] = Timer(1.0, tick, args=[code])
        timers[code].start()

# ✅ Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/create', methods=['POST'])
def create():
    code = request.form['game_code'].strip().upper()
    if not code or get_game(code):
        return 'Invalid or duplicate game code.'

    home_logo = request.files.get('home_logo')
    away_logo = request.files.get('away_logo')
    home_logo_path = away_logo_path = ''

    if home_logo:
        filename = secure_filename(home_logo.filename)
        home_logo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        home_logo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if away_logo:
        filename = secure_filename(away_logo.filename)
        away_logo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        away_logo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    game = Game(code=code, home_logo=home_logo_path, away_logo=away_logo_path)
    db.session.add(game)
    db.session.commit()
    session['logged_in'] = True
    return redirect(url_for('control_panel', code=code))

@app.route('/control/<code>', methods=['GET', 'POST'])
def control_panel(code):
    if not session.get('logged_in'):
        return render_template('control_login.html', code=code)
    game = get_game(code)
    if not game:
        return 'Game not found.'
    return render_template('control.html', game=game)

@app.route('/watch/<code>')
def display_panel(code):
    game = get_game(code)
    if not game:
        return 'Game not found.'
    return render_template('display.html', game=game)

@app.route('/end/<code>')
def end_game(code):
    game = get_game(code)
    if not game:
        return 'Game not found.'
    game.ended = True
    db.session.commit()
    return redirect(url_for('export_game', code=code))

@app.route('/export/<code>')
def export_game(code):
    game = get_game(code)
    if not game:
        return 'Game not found.'

    filename = f"{code}_summary.csv"
    filepath = os.path.join('static', filename)
    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Code', 'Home Team', 'Away Team', 'Score', 'Fouls', 'Period', 'Time'])
        writer.writerow([
            game.code,
            game.home_name,
            game.away_name,
            f"{game.home_score} - {game.away_score}",
            f"{game.home_fouls} - {game.away_fouls}",
            game.period,
            game.game_clock
        ])

    return send_file(filepath, as_attachment=True)

# ✅ SocketIO Events
@socketio.on('update_game')
def update_game(data):
    code = data['code']
    game = get_game(code)
    if game:
        for key, value in data['updates'].items():
            setattr(game, key, value)
        db.session.commit()
        emit('game_updated', data, to=code)

@socketio.on('join')
def on_join(data):
    join_room(data['code'])

@socketio.on('clock_control')
def clock_control(data):
    code = data['code']
    action = data['action']

    if action == 'start':
        if code not in timers:
            tick(code)
    elif action == 'pause':
        if code in timers:
            timers[code].cancel()
            del timers[code]
    elif action == 'reset':
        game = get_game(code)
        if game:
            game.game_clock = "10:00"
            game.shot_clock = 24
            db.session.commit()
            emit('game_updated', {
                'code': code,
                'updates': {
                    'game_clock': game.game_clock,
                    'shot_clock': game.shot_clock
                }
            }, to=code)
        if code in timers:
            timers[code].cancel()
            del timers[code]

# ✅ Create DB tables explicitly
with app.app_context():
    db.create_all()

# ✅ Dynamic port fallback for local, but respects Render PORT env
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 0))
    if port == 0:
        sock = socket.socket()
        sock.bind(('', 0))
        _, port = sock.getsockname()
        sock.close()
    socketio.run(app, host='0.0.0.0', port=port)
