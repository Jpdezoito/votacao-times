from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# -------------------------------
# CONFIGURAÇÃO DO BANCO POSTGRES
# -------------------------------

db_url = os.environ.get("DATABASE_URL")

# Ajuste necessário para alguns providers antigos (não é seu caso, mas deixo)
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Caso esteja rodando local sem DATABASE_URL, usa sqlite
if not db_url:
    db_url = "sqlite:///votacao.db"

engine = create_engine(db_url, future=True)


# -------------------------------
# FUNÇÕES AUXILIARES
# -------------------------------

def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


# -------------------------------
# CRIAÇÃO DAS TABELAS
# -------------------------------

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                nickname TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS players (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS votes (
                id SERIAL PRIMARY KEY,
                player_id INTEGER NOT NULL,
                score REAL NOT NULL,
                voter_name TEXT,
                UNIQUE(player_id, voter_name),
                FOREIGN KEY(player_id) REFERENCES players(id)
            )
        """))

init_db()


# -------------------------------
# ROTA RAIZ
# -------------------------------
@app.route("/")
def home():
    return jsonify({"message": "API funcionando com PostgreSQL!"})


# -------------------------------
# CADASTRO
# -------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()

    if not nickname or not password:
        return jsonify({"error": "Preencha apelido e senha"}), 400

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (nickname, password) VALUES (:nick, :pwd)"),
                {"nick": nickname, "pwd": hash_password(password)}
            )
            conn.execute(
                text("INSERT INTO players (name) VALUES (:name)"),
                {"name": nickname}
            )
        return jsonify({"ok": True})

    except IntegrityError:
        return jsonify({"error": "Apelido já está em uso"}), 400


# -------------------------------
# LOGIN
# -------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE nickname = :nick"),
            {"nick": nickname}
        ).mappings().first()

    if result and result["password"] == hash_password(password):
        return jsonify({"ok": True})

    return jsonify({"error": "Apelido ou senha incorretos"}), 400


# -------------------------------
# LISTAR PLAYERS
# -------------------------------
@app.route("/players", methods=["GET"])
def get_players():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.name,
                   COALESCE(AVG(v.score), 0) AS avg_score,
                   COUNT(v.id) AS votes
            FROM players p
            LEFT JOIN votes v ON v.player_id = p.id
            GROUP BY p.id, p.name
            ORDER BY p.name
        """)).mappings().all()

    players = []
    for r in rows:
        players.append({
            "id": r["id"],
            "name": r["name"],
            "avg_score": round(r["avg_score"], 2) if r["votes"] > 0 else None,
            "votes": r["votes"]
        })

    return jsonify(players)


# -------------------------------
# ADICIONAR PLAYER (se quiser usar depois)
# -------------------------------
@app.route("/players", methods=["POST"])
def add_player():
    data = request.get_json()
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Nome é obrigatório"}), 400

    with engine.begin() as conn:
        new_id = conn.execute(
            text("INSERT INTO players (name) VALUES (:name) RETURNING id"),
            {"name": name}
        ).scalar_one()

    return jsonify({"id": new_id, "name": name}), 201


# -------------------------------
# REMOVER PLAYER (apenas o próprio)
# -------------------------------
@app.route("/players/<int:player_id>", methods=["DELETE"])
def delete_player(player_id):
    # JSON esperado: { "requester": "apelido_logado" }
    data = request.get_json(silent=True) or {}
    requester = (data.get("requester") or "").strip()

    if not requester:
        return jsonify({"error": "Usuário não informado."}), 400

    with engine.begin() as conn:
        player = conn.execute(
            text("SELECT id, name FROM players WHERE id = :id"),
            {"id": player_id}
        ).mappings().first()

        if not player:
            return jsonify({"error": "Jogador não encontrado."}), 404

        # só permite remover o próprio cadastro
        if player["name"] != requester:
            return jsonify(
                {"error": "Você só pode remover o seu próprio cadastro."}
            ), 403

        # remove votos desse jogador
        conn.execute(
            text("DELETE FROM votes WHERE player_id = :id"),
            {"id": player_id}
        )

        # remove da tabela players
        conn.execute(
            text("DELETE FROM players WHERE id = :id"),
            {"id": player_id}
        )

        # remove também da tabela users (login)
        conn.execute(
            text("DELETE FROM users WHERE nickname = :nick"),
            {"nick": requester}
        )

    return jsonify({"ok": True})


# -------------------------------
# VOTAR
# -------------------------------
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

    with engine.connect() as conn:
        player = conn.execute(
            text("SELECT id, name FROM players WHERE id = :id"),
            {"id": player_id}
        ).mappings().first()

    if not player:
        return jsonify({"error": "Jogador não encontrado"}), 400

    # proíbe votar em si mesmo
    if voter_name and voter_name == player["name"]:
        return jsonify({"error": "Não é permitido votar em si mesmo."}), 400

    try:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM votes WHERE player_id = :pid AND voter_name = :vn"),
                {"pid": player_id, "vn": voter_name}
            ).mappings().first()

            if existing:
                conn.execute(
                    text("UPDATE votes SET score = :s WHERE id = :id"),
                    {"s": score, "id": existing["id"]}
                )
                updated = True
            else:
                conn.execute(
                    text("""
                        INSERT INTO votes (player_id, score, voter_name)
                        VALUES (:pid, :s, :vn)
                    """),
                    {"pid": player_id, "s": score, "vn": voter_name}
                )
                updated = False

        return jsonify({"ok": True, "updated": updated})

    except Exception as e:
        return jsonify({"error": "Erro interno ao gravar voto", "details": str(e)}), 500


# -------------------------------
# START
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
