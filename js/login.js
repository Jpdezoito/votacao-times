document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("loginForm");
    const nicknameInput = document.getElementById("nickname");
    const passwordInput = document.getElementById("password");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const nickname = nicknameInput.value.trim();
        const password = passwordInput.value.trim();

        if (!nickname || !password) {
            alert("Preencha apelido e senha.");
            return;
        }

        try {
            const res = await fetch(API_URL + "/login", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ nickname, password })
            });

            const data = await res.json();

            if (!res.ok) {
                alert(data.error || "Erro ao fazer login.");
                return;
            }

          setCurrentUser(nickname);
          setAdminFlag(!!data.is_admin);
          window.location = "votacao.html";

        } catch (err) {
            console.error(err);
            alert("Erro de conexão com o servidor.");
        }
    });
});
