from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

DEFAULT_ADMINS = ["maozinha"]


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
        # Tabela de usuários com flag de admin
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                nickname TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE
            )
        """))

        # Garante coluna is_admin mesmo se a tabela já existia
        conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE
        """))

        # Tabela de jogadores
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS players (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))

        # Tabela de votos
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

        # Marca os apelidos definidos como admins
        for nick in DEFAULT_ADMINS:
            conn.execute(
                text("UPDATE users SET is_admin = TRUE WHERE nickname = :nick"),
                {"nick": nick}
            )

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
        return jsonify({
            "ok": True,
            "is_admin": bool(result.get("is_admin", False))
        })

    return jsonify({"error": "Apelido ou senha incorretos"}), 400



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
            SELECT
                p.id,
                p.name,
                COALESCE(AVG(v.score), 0) AS avg_score,
                COUNT(v.id) AS votes,
                COALESCE(u.is_admin, FALSE) AS is_admin
            FROM players p
            LEFT JOIN votes v ON v.player_id = p.id
            LEFT JOIN users u ON u.nickname = p.name
            GROUP BY p.id, p.name, u.is_admin
            ORDER BY p.name
        """)).mappings().all()

    players = []
    for r in rows:
        players.append({
            "id": r["id"],
            "name": r["name"],
            "avg_score": round(r["avg_score"], 2) if r["votes"] > 0 else None,
            "votes": r["votes"],
            "is_admin": bool(r["is_admin"])
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

        # pega info de quem está pedindo
        req_user = conn.execute(
            text("SELECT is_admin FROM users WHERE nickname = :nick"),
            {"nick": requester}
        ).mappings().first()

        if not req_user:
            return jsonify({"error": "Usuário solicitante não encontrado."}), 404

        is_admin = bool(req_user["is_admin"])

        # só pode remover se for o próprio ou admin
        if (player["name"] != requester) and (not is_admin):
            return jsonify(
                {"error": "Você só pode remover o seu próprio cadastro."}
            ), 403

        # apaga votos desse jogador
        conn.execute(
            text("DELETE FROM votes WHERE player_id = :id"),
            {"id": player_id}
        )

        # apaga da tabela players
        conn.execute(
            text("DELETE FROM players WHERE id = :id"),
            {"id": player_id}
        )

        # apaga da tabela users (login) do jogador removido
        conn.execute(
            text("DELETE FROM users WHERE nickname = :nick"),
            {"nick": player["name"]}
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
    
    

@app.route("/set_admin", methods=["POST"])
def set_admin():
    data = request.get_json()
    requester = (data.get("requester") or "").strip()
    target = (data.get("target") or "").strip()
    make_admin = bool(data.get("is_admin", True))

    if not requester or not target:
        return jsonify({"error": "Dados inválidos."}), 400

    with engine.begin() as conn:
        # verifica se quem está pedindo é admin
        req_user = conn.execute(
            text("SELECT is_admin FROM users WHERE nickname = :nick"),
            {"nick": requester}
        ).mappings().first()

        if not req_user or not req_user["is_admin"]:
            return jsonify({"error": "Apenas administradores podem alterar privilégios."}), 403

        user = conn.execute(
            text("SELECT id FROM users WHERE nickname = :nick"),
            {"nick": target}
        ).mappings().first()

        if not user:
            return jsonify({"error": "Usuário alvo não encontrado."}), 404

        conn.execute(
            text("UPDATE users SET is_admin = :adm WHERE nickname = :nick"),
            {"adm": make_admin, "nick": target}
        )

    return jsonify({"ok": True})

# -------------------------------
# START
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
