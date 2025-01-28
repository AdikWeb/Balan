from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import os
import random
import string

app = Flask(__name__)
socketio = SocketIO(app)

JSON_FILE = 'lobbies.json'

def load_lobbies():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r') as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    return {}

def save_lobbies(lobbies):
    with open(JSON_FILE, 'w') as f:
        json.dump(lobbies, f)

lobbies = load_lobbies()

def generate_lobby_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_lobby', methods=['POST'])
def create_lobby():
    lobby_code = generate_lobby_code()
    while lobby_code in lobbies:
        lobby_code = generate_lobby_code()
    lobbies[lobby_code] = {"players": {}, "host": None}
    save_lobbies(lobbies)
    return jsonify({"success": True, "lobby_code": lobby_code})

@app.route('/join_lobby/<lobby_code>')
def join_lobby(lobby_code):
    if lobby_code in lobbies:
        return render_template('lobby.html', lobby_code=lobby_code)
    return "Lobby not found", 404
@app.route('/join', methods=['POST'])
@app.route('/join', methods=['POST'])
def join():
    name = request.json['name']
    lobby_code = request.json['lobby_code']
    if lobby_code not in lobbies:
        return jsonify({"success": False, "message": "Lobby not found"})
    if name in lobbies[lobby_code]["players"]:
        # Игрок уже в лобби, просто возвращаем успех
        return jsonify({"success": True, "isHost": name == lobbies[lobby_code]["host"]})
    lobbies[lobby_code]["players"][name] = {"ratings": {}}
    if "host" not in lobbies[lobby_code] or lobbies[lobby_code]["host"] is None:
        lobbies[lobby_code]["host"] = name
    save_lobbies(lobbies)
    return jsonify({"success": True, "isHost": name == lobbies[lobby_code]["host"]})


@app.route('/get_players/<lobby_code>', methods=['GET'])
def get_players(lobby_code):
    if lobby_code in lobbies:
        return jsonify({
            "players": list(lobbies[lobby_code]["players"].keys()),
            "host": lobbies[lobby_code]["host"]
        })
    return jsonify({"players": [], "host": None})
@app.route('/rate', methods=['POST'])
@app.route('/reset_rating', methods=['POST'])
def reset_rating():
    rater = request.json['rater']
    rated = request.json['rated']
    lobby_code = request.json['lobby_code']

    if lobby_code not in lobbies or rater not in lobbies[lobby_code]["players"] or rated not in lobbies[lobby_code]["players"]:
        return jsonify({"success": False, "message": "Invalid lobby or player"})

    if rated in lobbies[lobby_code]["players"][rater]["ratings"]:
        del lobbies[lobby_code]["players"][rater]["ratings"][rated]
        save_lobbies(lobbies)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Rating not found"})


@app.route('/get_average_ratings/<lobby_code>', methods=['GET'])
def get_average_ratings(lobby_code):
    if lobby_code not in lobbies:
        return jsonify({"error": "Lobby not found"}), 404

    average_ratings = {}
    for player in lobbies[lobby_code]["players"]:
        ratings = [rating for other_player, other_player_data in lobbies[lobby_code]["players"].items()
                   for rated, rating in other_player_data.get("ratings", {}).items()
                   if rated == player]
        if ratings:
            average_ratings[player] = sum(ratings) / len(ratings)
        else:
            average_ratings[player] = 5  # Default rating if no ratings given

    return jsonify(average_ratings)


@app.route('/divide_teams', methods=['POST'])
def divide_teams():
    lobby_code = request.json['lobby_code']
    num_teams = request.json.get('num_teams', 2)
    if lobby_code not in lobbies:
        return jsonify({"success": False, "message": "Lobby not found"})

    average_ratings = get_average_ratings(lobby_code).json
    sorted_players = sorted(average_ratings.items(), key=lambda x: x[1], reverse=True)

    teams = [[] for _ in range(num_teams)]
    team_ratings = [0] * num_teams

    for player, rating in sorted_players:
        # Находим команду с наименьшим суммарным рейтингом
        target_team = min(range(num_teams), key=lambda i: team_ratings[i])
        teams[target_team].append(player)
        team_ratings[target_team] += rating
    return jsonify({"success": True, "teams": teams})

@app.route('/remove_player', methods=['POST'])
def remove_player():
    player = request.json['player']
    lobby_code = request.json['lobby_code']

    if lobby_code not in lobbies or player not in lobbies[lobby_code]["players"]:
        return jsonify({"success": False, "message": "Invalid lobby or player"})

    del lobbies[lobby_code]["players"][player]

    # If the removed player was the host, assign a new host
    if lobbies[lobby_code]["host"] == player:
        if lobbies[lobby_code]["players"]:
            lobbies[lobby_code]["host"] = next(iter(lobbies[lobby_code]["players"]))
        else:
            lobbies[lobby_code]["host"] = None

    save_lobbies(lobbies)
    return jsonify({"success": True})


@socketio.on('join')
def on_join(data):
    room = data['lobby_code']
    join_room(room)

@socketio.on('teams_divided')
def on_teams_divided(data):
    room = data['lobby_code']
    emit('teams_divided', data, room=room)
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=27100)

