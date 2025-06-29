import os
import uuid
import socket
from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory, flash
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# --- Flask setup ---
app = Flask(__name__)
app.secret_key = 'super_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/games.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
socketio = SocketIO(app, async_mode='eventlet')

# --- Ensure upload folder exists ---
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs("instance", exist_ok=True)

# --- DB Setup ---
db = SQLAlchemy(app)

class Game(db.Model):
    code = db.Column(db.String(10), primary_key=True)
    home_team = db.Column(db.String(50))
    away_team = db.Column(db.String(50))
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    home_fouls = db.Column(db.Integer, default=0)
    away_fouls = db.Column(db.Integer, default=0)
    period = db.Column(db.Integer, default=1)
    game_clock = db.Column(db.String(10), default='10:00')
    shot_clock = db.Column(db.String(5), default='24')
    home_logo = db.Column(db.String(200), nullable=True)
    away_logo = db.Column(db.String(200), nullable=True)
    password = db.Column(db.String(50), nullable=True)

with app.app_context():
    db.create_all()

# --- Routes ---

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        code = request.form['code'].strip().lower()
        if Game.query.get(code):
            return "Game code already exists"
        
        home_team = request.form['home_team']
        away_team = request.form['away_team']
        password = request.form.get('password', '')
        
        # Handle logo upload
        home_logo = request.files.get('home_logo')
        away_logo = request.files.get('away_logo')
        home_logo_path = save_logo(home_logo, code + '_home') if home_logo else None
        away_logo_path = save_logo(away_logo, code + '_away') if away_logo else None

        game = Game(code=code, home_team=home_team, away_team=away_team,
                    home_logo=home_logo_path, away_logo=away_logo_path,
                    password=password)
        db.session.add(game)
        db.session.commit()
        session[code] = password
        return redirect(url_for('control', code=code))
    return render_template('create.html')

@app.route('/watch', methods=['GET', 'POST'])
def watch():
    if request.method == 'POST':
        code = request.form['code'].strip().lower()
        game = Game.query.get(code)
        if game:
            return redirect(url_for('display', code=code))
        else:
            return "Invalid game code."
    return render_template('watch.html')

@app.route('/control/<code>', methods=['GET', 'POST'])
def control(code):
    game = Game.query.get(code)
    if not game:
        return "Game not found"
    if session.get(code) != game.password:
        if request.method == 'POST':
            password = request.form.get('password')
            if password == game.password:
                session[code] = password
                return redirect(url_for('control', code=code))
            else:
                flash("Incorrect password")
        return render_template('password.html', code=code)
    return render_template('control.html', code=code, game=game)

@app.route('/display/<code>')
def display(code):
    game = Game.query.get(code)
    if not game:
        return "Game not found"
    return render_template('display.html', code=code, game=game)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def save_logo(file, prefix):
    if file and file.filename:
        filename = secure_filename(prefix + '_' + file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return '/' + filepath
    return None

# --- SocketIO Events ---

@socketio.on('join')
def on_join(data):
    room = data['code']
    join_room(room)

@socketio.on('update')
def on_update(data):
    room = data['code']
    game = Game.query.get(room)
    if game:
        game.home_score = data['home_score']
        game.away_score = data['away_score']
        game.home_fouls = data['home_fouls']
        game.away_fouls = data['away_fouls']
        game.period = data['period']
        game.game_clock = data['game_clock']
        game.shot_clock = data['shot_clock']
        db.session.commit()
        emit('update', data, to=room)

@socketio.on('buzzer')
def on_buzzer(data):
    emit('buzzer', {}, to=data['code'])

# --- Dynamic Port Handling ---

def find_free_port(start_port=5000, max_tries=10):
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise OSError("No free ports available")

if __name__ == '__main__':
    selected_port = int(os.environ.get("PORT", find_free_port()))
    print(f"✅ Starting app on port {selected_port}")
    socketio.run(app, host='0.0.0.0', port=selected_port)
