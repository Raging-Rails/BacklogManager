"""This module implements many different secure hash and message digest algorithms."""
import hashlib
import uuid
import requests
import json
from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.sql.expression import func
# pip install flask flask_sqlalchemy psycopg2 flask_cors
rankings = {}

app = Flask(__name__)
CORS(app)

# Connection: MAKE SURE TO REPLACE USERNAME:PASSWORD WITH THE ONE SET UP ON YOUR OWN DEVICE
# SSH Tunnel Forward to Local Port: ssh -L 5433:127.0.0.1:5432 USERNAME@128.113.126.87
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://knighk4:1234@localhost/backlog_manager'

db = SQLAlchemy(app)

RAWG_QUERY_URL = "https://api.rawg.io/api/games"
RAWG_GAME_DETAILS_URL = "https://api.rawg.io/api/games/{}"
API_KEY = "1af69e1cf8664df59d23e49cd5aca2ea"

'''
example use of RAWG API call
url = f"https://api.rawg.io/api/platforms?key={API_KEY}"
response = requests.get(url)
data = response.json()
print(data)
'''

class Users(db.Model):
    """Define basic users table with columns: email, name, hashed passwords, and session token."""
    email = db.Column(db.String(100), unique=True, nullable=False, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    session_token = db.Column(db.String(200), unique=True, nullable=True)

    def __repr__(self):
        return f'<User {self.email}>'

    def set_password(self, password: str):
        """Hashes and stores the password."""
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, input_password: str) -> bool:
        """Checks if the given password matches the stored hash."""
        return self.password_hash == hashlib.sha256(input_password.encode()).hexdigest()

class Preferences(db.Model):
    """Temporary table for user preferences."""
    email = db.Column(db.String(100), unique=True, nullable=False, primary_key=True)
    preferences = db.Column(db.JSON, nullable=False)

    def __repr__(self):
        return f'<User {self.email}>'

class Library(db.Model):
    """Game Library table with columns: email and gameid."""
    email = db.Column(db.String(100), nullable=False, primary_key=True)
    gameid = db.Column(db.Integer(), nullable=False, primary_key=True)

    def __repr__(self):
        return f'<Library {self.email}>'

class Game(db.Model):
    """Game table with columns:
    id, name, platform, genre, release date, description, and a image.
    """
    id = db.Column(db.Integer(), unique=True, nullable=False, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    platform = db.Column(db.String(200), nullable=False)
    genre = db.Column(db.String(200), nullable=False)
    release_date = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    image = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<Game {self.name}>'

# Creates tables in the database (one-time setup for now)
with app.app_context():
    db.create_all()

# Allow requests from frontend
CORS(app, resources={r"/*": {"origins": "http://128.113.126.87:3000"}})

@app.route('/register', methods=['POST'])
def register():
    """API route to register a new user: http://127.0.0.1:5000/register."""
    data = request.json
    # Checks if user exists first
    existing_user = Users.query.filter((Users.email == data['email'])).first()
    if existing_user:
        return jsonify({"error": "User already exists!"}), 400
    # Adding new user
    new_user = Users(email=data['email'], name=data['name'])
    new_user.set_password(data['password'])
    token = generate_token()
    db.session.add(new_user)
    new_user.session_token = token
    db.session.commit()
    return jsonify({'token': token}), 201

@app.route('/login', methods=['POST'])
def login():
    """API route to login a user: http://127.0.0.1:5000/login."""
    data = request.json
    user = Users.query.filter_by(email=data['email']).first()
    # Checks if users and their password matches
    if user and user.verify_password(data['password']):
        token = generate_token()
        user.session_token = token
        db.session.commit()
        return jsonify({'token': token}), 200
    return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/add-game', methods=['POST'])
def add_game():
    """WPI API route to add game for a user: http://127.0.0.1:5000/add-game."""
    data = request.json
    token = data['token']
    rawg_id = data['game_id']

    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    # Check if the user already owns the game
    existing = Library.query.filter_by(email=user.email, gameid=rawg_id).first()
    if existing:
        return jsonify({'message': 'Game already added'})

    new_entry = Library(email=user.email, gameid=rawg_id)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({'message': 'Game added successfully'})

@app.route('/delete-game', methods=['POST'])
def delete_game():
    """WPI API route to delete game for a user: http://127.0.0.1:5000/delete-game."""
    data = request.json
    token = data['token']
    rawg_id = data['game_id']

    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    # Check if the user already owns the game
    game = Library.query.filter_by(email=user.email, gameid=rawg_id).first()
    if not game:
        return jsonify({'message': 'Game not found in library'})

    db.session.delete(game)
    db.session.commit()

    return jsonify({'message': 'Game deleted successfully'})

@app.route('/get-games-library', methods=['POST', 'OPTIONS'])
def get_game_library():
    """WPI API route to add game for a user: http://127.0.0.1:5000//get-games-library."""
    if request.method == 'OPTIONS':
        return '', 200
    data = request.json
    token = data['token']

    # Verify the token
    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    user_games = Library.query.filter_by(email=user.email).all()
    game_ids = [entry.gameid for entry in user_games]
    results = []
    for game_id in game_ids:
        response = requests.get(RAWG_GAME_DETAILS_URL.format(game_id), params={'key': API_KEY})
        if response.status_code == 200:
            game_data = response.json()
            results.append({'id': game_data['id'], 'name': game_data['name']})
    json_data = json.dumps(results)
    return Response(json_data, content_type='application/json')

@app.route('/search-games', methods=['POST'])
def search_games():
    """WPI API route to add game for a user: http://127.0.0.1:5000//search-games."""
    data = request.json
    search_query = data['query']
    params = {
        'key': API_KEY,  
        'search': search_query
    }
    response = requests.get(RAWG_QUERY_URL, params=params)
    results = response.json().get('results', [])
    games = [{'id': game['id'], 'name': game['name']} for game in results]
    return jsonify({'results': games})

@app.route('/save-default-preferences', methods=['POST'])
def save_default_preferences():
    """Saves user preferences to the database."""
    data = request.json
    token = data['token']
    preferences = data['preferences']

    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    existing_preferences = Preferences.query.filter_by(email=user.email).first()
    if existing_preferences:
        existing_preferences.preferences = preferences
    else:
        new_preferences = Preferences(email=user.email, preferences=preferences)
        db.session.add(new_preferences)

    db.session.commit()
    return jsonify({'message': 'Preferences saved successfully'})

@app.route('/parse-preferences', methods=['POST'])
def parse_preferences():
    """Ranks games based on the user's owned games and preferences, then sends ranking to frontend."""
    if request.method == 'OPTIONS':
        return '', 200
    data = request.json
    token = data['token']
    preferences = data['preferences']

    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    user_games = Library.query.filter_by(email=user.email).all()
    if not user_games:
        print("nope")
        return jsonify({'error': 'No owned games found'}), 404

    game_ids = [game.gameid for game in user_games]
    create_ranking(preferences, game_ids, user)
    return jsonify({"message": "Ranking sent to frontend"})

@app.route('/receive-ranking', methods=['POST'])
def receive_ranking():
    """Returns the stored ranking of games."""
    if request.method == 'OPTIONS':
        return '', 200
    data = request.json
    token = data['token']

    user = Users.query.filter_by(session_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 401

    if user.email not in rankings:
        return jsonify({'error': 'No ranking found'}), 404
    return jsonify({"ranked_games": rankings[user.email]})

@app.route('/get-game-stats', methods=['POST'])
def get_game_stats():
    data = request.json
    game_id = data['game_id']
    response = requests.get(RAWG_GAME_DETAILS_URL.format(game_id), params={'key': API_KEY})
    if response.status_code == 200:
        game_data = response.json()
        game_stats = {'title': game_data['name'],
                      'rating': game_data['rating'],
                      'cover': game_data['background_image'],
                      'releaseDate': game_data['released'],
                      'developer': [dev['name'] for dev in game_data['developers']],
                      'genres': [genre['name'] for genre in game_data['genres']],
                      'platforms': [plat['platform']['name'] for plat in game_data['platforms']],
                      'reviews': game_data['ratings']}     
    return jsonify({'game_stats': game_stats})

def create_ranking(preferences, game_ids, user):
    """Creates a game ranking."""
    ranked_games = []
    for game_id in game_ids:
        response = requests.get(RAWG_GAME_DETAILS_URL.format(game_id), params={'key': API_KEY})
        if response.status_code == 200:
            game_data = response.json()
            ranked_games.append({'id': game_id, 'weight': weight_game(preferences, game_data), 'name': game_data['name']})
    ranked_games.sort(key=lambda x: x['weight'], reverse=True)
    rankings[user.email] = ranked_games
    return ranked_games

def weight_game(preferences, game_data):
    """Weights a game based on user preferences."""
    weight = 100
    weight = weight - abs(preferences['completionTime'] - game_data['playtime'])
    if game_data['esrb_rating']['name'] == preferences['esrbRating']:
        weight += 50
    for platform in game_data['platforms']:
        if platform['name'] == preferences['platform']:
            weight += 50
    if game_data['genre'] == preferences['genre']:
        weight += 50
    if preferences['use_reviews']:
        weight += game_data['metacritic']
    return weight

def generate_token():
    """Generates a new session token."""
    return str(uuid.uuid4())

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)
