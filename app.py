from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

games = {}

def create_default_game():
    return {
        'home_score': 0,
        'away_score': 0,
        'home_fouls': 0,
        'away_fouls': 0,
        'period': 1,
        'home_name': 'Home',
        'away_name': 'Away'
    }

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/create', methods=['POST'])
def create_game():
    code = request.form['game_code'].upper().strip()
    if not code or code in games:
        return "Invalid or duplicate game code."
    games[code] = create_default_game()
    return redirect(url_for('control', game_code=code))

@app.route('/control/<game_code>')
def control(game_code):
    if game_code not in games:
        return "Game not found."
    return render_template('control.html', game_code=game_code)

@app.route('/display/<game_code>')
def display(game_code):
    if game_code not in games:
        return "Game not found."
    return render_template('display.html', game_code=game_code)

# SocketIO events will be added later

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

from threading import Timer

# Store timers globally per game
clocks = {}

@socketio.on('join_game')
def on_join(data):
    game_code = data['game_code']
    if game_code in games:
        emit('update_display', games[game_code], broadcast=False)

@socketio.on('update_score')
def update_score(data):
    game_code = data['game_code']
    field = data['field']
    change = int(data['change'])

    if game_code in games:
        games[game_code][field] += change
        emit('update_display', games[game_code], broadcast=True)

@socketio.on('clock_control')
def handle_clock(data):
    game_code = data['game_code']
    action = data['action']

    if game_code not in games:
        return

    if 'clock_time' not in games[game_code]:
        games[game_code]['clock_time'] = 0

    def tick():
        if game_code not in clocks:
            return
        games[game_code]['clock_time'] += 1
        minutes = games[game_code]['clock_time'] // 60
        seconds = games[game_code]['clock_time'] % 60
        games[game_code]['clock'] = f"{minutes:02d}:{seconds:02d}"
        emit('update_display', games[game_code], broadcast=True)
        clocks[game_code] = Timer(1, tick)
        clocks[game_code].start()

    if action == 'start':
        if game_code not in clocks:
            tick()
    elif action == 'pause':
        if game_code in clocks:
            clocks[game_code].cancel()
            del clocks[game_code]
    elif action == 'reset':
        games[game_code]['clock_time'] = 0
        games[game_code]['clock'] = "00:00"
        if game_code in clocks:
            clocks[game_code].cancel()
            del clocks[game_code]
        emit('update_display', games[game_code], broadcast=True)
