from flask import Flask, render_template, request, redirect, session, url_for, flash, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super_secret_key'
socketio = SocketIO(app)

# === DATABASE PATH FIX ===
if os.environ.get('RENDER'):
    db_path = '/tmp/games.db'  # Only writable folder on Render
else:
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'games.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# === DB MODEL ===
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    home_name = db.Column(db.String(50), default='Home')
    away_name = db.Column(db.String(50), default='Away')
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    home_fouls = db.Column(db.Integer, default=0)
    away_fouls = db.Column(db.Integer, default=0)
    home_timeouts = db.Column(db.Integer, default=0)
    away_timeouts = db.Column(db.Integer, default=0)
    period = db.Column(db.Integer, default=1)
    game_clock = db.Column(db.String(10), default='10:00')
    shot_clock = db.Column(db.String(10), default='24')
    home_logo = db.Column(db.String(200), default='')
    away_logo = db.Column(db.String(200), default='')

# === ENSURE DB IS CREATED ===
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"DB Creation Error: {e}")

# === ROUTES ===
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/create', methods=['GET', 'POST'])
def create_game():
    if request.method == 'POST':
        code = request.form['game_code'].strip().upper()
        password = request.form['password']
        if not code or Game.query.filter_by(code=code).first():
            flash('Invalid or duplicate game code.')
            return redirect(url_for('create_game'))

        new_game = Game(code=code)
        db.session.add(new_game)
        db.session.commit()
        session['auth'] = code + password
        return redirect(url_for('control', code=code))

    return render_template('create_game.html')

@app.route('/control/<code>', methods=['GET'])
def control(code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return 'Invalid game code', 404
    return render_template('control.html', game=game)

@app.route('/display/<code>')
def display(code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return 'Invalid game code', 404
    return render_template('display.html', game=game)

@app.route('/watch', methods=['GET', 'POST'])
def watch():
    if request.method == 'POST':
        code = request.form['game_code'].strip().upper()
        game = Game.query.filter_by(code=code).first()
        if game:
            return redirect(url_for('display', code=code))
        else:
            flash('Invalid Game Code')
            return redirect(url_for('watch'))
    return render_template('watch.html')

@app.route('/upload_logo/<team>/<code>', methods=['POST'])
def upload_logo(team, code):
    game = Game.query.filter_by(code=code).first()
    if not game:
        return 'Invalid game code', 404

    file = request.files['logo']
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if team == 'home':
            game.home_logo = '/' + filepath
        elif team == 'away':
            game.away_logo = '/' + filepath

        db.session.commit()
        emit('update', {'game': game_as_dict(game)}, room=code, namespace='/')
        return redirect(url_for('control', code=code))

    return 'No file uploaded', 400

# === SOCKET EVENTS ===
@socketio.on('join')
def on_join(data):
    code = data['code']
    join_room(code)

@socketio.on('update')
def on_update(data):
    code = data['code']
    game = Game.query.filter_by(code=code).first()
    if game:
        for key in data:
            if hasattr(game, key):
                setattr(game, key, data[key])
        db.session.commit()
        emit('update', {'game': game_as_dict(game)}, room=code)

@socketio.on('buzzer')
def on_buzzer(data):
    code = data['code']
    emit('buzzer', {}, room=code)

# === HELPER ===
def game_as_dict(game):
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

# === MAIN ===
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
