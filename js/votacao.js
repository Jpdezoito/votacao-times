let currentUser = null;
let isAdmin = false;
let playersCache = [];

document.addEventListener("DOMContentLoaded", () => {
    const user = requireAuth();
    if (!user) return;

    currentUser = user;
    isAdmin = getAdminFlag();

    document.getElementById("currentUserName").textContent = currentUser;
    document.getElementById("btnLogout").addEventListener("click", () => logout());
    document.getElementById("btnDeleteAccount").addEventListener("click", () => deleteOwnAccount());

    loadPlayers();
});

async function loadPlayers() {
    try {
        const res = await fetch(API_URL + "/players");
        playersCache = await res.json();
        renderTable();
    } catch (err) {
        console.error(err);
        alert("Erro ao carregar jogadores.");
    }
}

function renderTable() {
    const tbody = document.getElementById("playersBody");
    tbody.innerHTML = "";

    playersCache.forEach(p => {
        const tr = document.createElement("tr");

        // Jogador
        const tdName = document.createElement("td");
        tdName.textContent = p.name;
        tr.appendChild(tdName);

        // Campo de nota
        const tdInput = document.createElement("td");
        const input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.max = "10";
        input.step = "0.1";
        input.id = "nota_" + p.id;
        tdInput.appendChild(input);
        tr.appendChild(tdInput);

        // Botão votar
        const tdAction = document.createElement("td");
        const btnVote = document.createElement("button");
        btnVote.textContent = "Votar";
        btnVote.className = "btn btn-primary btn-sm";
        btnVote.onclick = () => votePlayer(p.id);
        tdAction.appendChild(btnVote);
        tr.appendChild(tdAction);

        // Média
        const tdMedia = document.createElement("td");
        tdMedia.id = "media_" + p.id;
        tdMedia.textContent =
            (p.votes > 0 && p.avg_score != null) ? p.avg_score.toFixed(2) : "-";
        tr.appendChild(tdMedia);

        // Votos
        const tdVotos = document.createElement("td");
        tdVotos.id = "votos_" + p.id;
        tdVotos.textContent = p.votes;
        tr.appendChild(tdVotos);

        // Coluna ADMIN
        const tdAdmin = document.createElement("td");
        if (isAdmin) {
            if (p.name === currentUser) {
                tdAdmin.textContent = "Admin (você)";
            } else {
                const btnAdm = document.createElement("button");
                btnAdm.className = "btn btn-secondary btn-sm";
                btnAdm.textContent = p.is_admin ? "Remover ADM" : "Tornar ADM";
                btnAdm.onclick = () => toggleAdmin(p.name, !p.is_admin);
                tdAdmin.appendChild(btnAdm);
            }
        } else {
            tdAdmin.textContent = p.is_admin ? "Admin" : "-";
        }
        tr.appendChild(tdAdmin);

        // Coluna REMOVER
        const tdRemove = document.createElement("td");

        // Jogador normal NÃO tem X na tabela; só exclui pela barra de cima
        if (isAdmin && p.name !== currentUser) {
            const btnDel = document.createElement("button");
            btnDel.textContent = "X";
            btnDel.className = "btn btn-danger btn-sm";
            btnDel.onclick = () => adminRemovePlayer(p.id, p.name);
            tdRemove.appendChild(btnDel);
        } else {
            tdRemove.textContent = "-";
        }

        tr.appendChild(tdRemove);

        tbody.appendChild(tr);
    });
}

async function votePlayer(id) {
    const input = document.getElementById("nota_" + id);
    const nota = parseFloat(input.value);

    if (isNaN(nota) || nota < 0 || nota > 10) {
        alert("Digite uma nota entre 0 e 10.");
        return;
    }

    try {
        const res = await fetch(API_URL + "/vote", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                player_id: id,
                score: nota,
                voter: currentUser
            })
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            alert(data.error || "Erro ao votar.");
            return;
        }

        input.value = "";
        await loadPlayers();
    } catch (err) {
        console.error(err);
        alert("Erro ao enviar voto.");
    }
}

// ======== EXCLUIR A PRÓPRIA CONTA ========

async function deleteOwnAccount() {
    const player = playersCache.find(p => p.name === currentUser);
    if (!player) {
        alert("Erro: seu jogador não foi encontrado na lista.");
        return;
    }

    if (!confirm("Tem certeza que deseja excluir SUA conta?\nTodos os seus votos serão apagados.")) {
        return;
    }

    try {
        const res = await fetch(API_URL + "/players/" + player.id, {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ requester: currentUser })
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            alert(data.error || "Erro ao excluir conta.");
            return;
        }

        alert("Sua conta foi removida.");
        logout();
    } catch (err) {
        console.error(err);
        alert("Erro ao excluir conta.");
    }
}

// ======== ADMIN: REMOVER QUALQUER JOGADOR ========

async function adminRemovePlayer(id, name) {
    if (!isAdmin) return;

    if (!confirm(`Excluir a conta do jogador "${name}" e todos os votos dele?`)) {
        return;
    }

    try {
        const res = await fetch(API_URL + "/players/" + id, {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ requester: currentUser })
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            alert(data.error || "Erro ao excluir jogador.");
            return;
        }

        await loadPlayers();
    } catch (err) {
        console.error(err);
        alert("Erro ao excluir jogador.");
    }
}

// ======== ADMIN: PROMOVER / TIRAR ADMIN ========

async function toggleAdmin(targetName, makeAdmin) {
    if (!isAdmin) return;

    const msg = makeAdmin
        ? `Tornar "${targetName}" administrador?`
        : `Remover privilégios de administrador de "${targetName}"?`;

    if (!confirm(msg)) return;

    try {
        const res = await fetch(API_URL + "/set_admin", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                requester: currentUser,
                target: targetName,
                is_admin: makeAdmin
            })
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            alert(data.error || "Erro ao alterar privilégios.");
            return;
        }

        await loadPlayers();
    } catch (err) {
        console.error(err);
        alert("Erro ao alterar privilégios.");
    }
}
