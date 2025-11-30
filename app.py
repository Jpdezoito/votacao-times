from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)  # permite acesso do seu HTML (Live Server / outro host)

DB_NAME = "votacao.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

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
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
    """)

    conn.commit()
    conn.close()


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

    try:
        score = float(score)
    except (TypeError, ValueError):
        return jsonify({"error": "Nota inválida"}), 400

    if score < 0 or score > 10:
        return jsonify({"error": "Nota deve ser entre 0 e 10"}), 400

    conn = get_db()
    cur = conn.cursor()

    # verifica se player existe
    cur.execute("SELECT id FROM players WHERE id = ?", (player_id,))
    if cur.fetchone() is None:
        conn.close()
        return jsonify({"error": "Jogador não encontrado"}), 404

    cur.execute("INSERT INTO votes (player_id, score) VALUES (?, ?)",
                (player_id, score))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
