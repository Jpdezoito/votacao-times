from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import hashlib

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DB_NAME = "votacao.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            score REAL NOT NULL,
            voter_name TEXT,
            FOREIGN KEY(player_id) REFERENCES players(id),
            UNIQUE(player_id, voter_name)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------------------------------------------------
# RAIZ
# ------------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"message": "API funcionando! Acesse /players, /register, /login, /vote, etc."})

# ------------------------------------------------------------
# CADASTRO
# ------------------------------------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()

    if not nickname or not password:
        return jsonify({"error": "Preencha apelido e senha"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        # cria o usuário (login)
        cur.execute(
            "INSERT INTO users (nickname, password) VALUES (?, ?)",
            (nickname, hash_password(password))
        )
        # cria também o jogador com o mesmo apelido
        cur.execute(
            "INSERT INTO players (name) VALUES (?)",
            (nickname,)
        )

        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Apelido já está em uso"}), 400


# ------------------------------------------------------------
# LOGIN
# ------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
    user = cur.fetchone()

    if user and user["password"] == hash_password(password):
        return jsonify({"ok": True})

    return jsonify({"error": "Apelido ou senha incorretos"}), 400


# ------------------------------------------------------------
# RESTO DO CÓDIGO DA VOTAÇÃO (igual ao anterior)
# ------------------------------------------------------------

@app.route("/players", methods=["GET"])
def get_players():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.name,
               IFNULL(AVG(v.score), 0) AS avg_score,
               COUNT(v.id) AS votes
        FROM players p
        LEFT JOIN votes v ON v.player_id = p.id
        GROUP BY p.id, p.name
        ORDER BY p.name
    """)

    rows = cur.fetchall()
    conn.close()

    players = []
    for r in rows:
        players.append({
            "id": r["id"],
            "name": r["name"],
            "avg_score": round(r["avg_score"], 2) if r["votes"] > 0 else None,
            "votes": r["votes"]
        })

    return jsonify(players)


@app.route("/players", methods=["POST"])
def add_player():
    data = request.get_json()
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Nome é obrigatório"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO players (name) VALUES (?)", (name,))
    conn.commit()
    player_id = cur.lastrowid
    conn.close()

    return jsonify({"id": player_id, "name": name}), 201


@app.route("/players/<int:player_id>", methods=["DELETE"])
def delete_player(player_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM votes WHERE player_id = ?", (player_id,))
    cur.execute("DELETE FROM players WHERE id = ?", (player_id,))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/vote", methods=["POST"])
def vote():
    data = request.get_json()
    player_id = data.get("player_id")
    score = data.get("score")
    voter_name = (data.get("voter") or "").strip()

    try:
        score = float(score)
    except:
        return jsonify({"error": "Nota inválida"}), 400

    if score < 0 or score > 10:
        return jsonify({"error": "Nota deve ser entre 0 e 10"}), 400

    conn = get_db()
    cur = conn.cursor()
    # validações adicionais
    if player_id is None:
        conn.close()
        return jsonify({"error": "player_id é obrigatório"}), 400

    # garante que o jogador exista
    cur.execute("SELECT id FROM players WHERE id = ?", (player_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Jogador não encontrado"}), 400

    try:
        cur.execute("INSERT INTO votes (player_id, score, voter_name) VALUES (?, ?, ?)",
                    (player_id, score, voter_name))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Você já votou neste jogador!"}), 400
    except Exception as e:
        # captura outras exceções e retorna mensagem para debugging
        conn.close()
        return jsonify({"error": "Erro interno ao gravar voto", "details": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
