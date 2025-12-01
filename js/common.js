const API_URL = "https://votacao-times.onrender.com";

const STORAGE_KEY = "votacao_user_name";
const ADMIN_KEY   = "votacao_is_admin";

function setCurrentUser(name) {
    localStorage.setItem(STORAGE_KEY, name);
}

function getCurrentUser() {
    return localStorage.getItem(STORAGE_KEY);
}

function clearCurrentUser() {
    localStorage.removeItem(STORAGE_KEY);
}

function setAdminFlag(isAdmin) {
    localStorage.setItem(ADMIN_KEY, isAdmin ? "1" : "0");
}

function getAdminFlag() {
    return localStorage.getItem(ADMIN_KEY) === "1";
}

function clearAdminFlag() {
    localStorage.removeItem(ADMIN_KEY);
}

function requireAuth() {
    const user = getCurrentUser();
    if (!user) {
        window.location = "login.html";
        return null;
    }
    return user;
}

function logout() {
    clearCurrentUser();
    clearAdminFlag();
    window.location = "login.html";
}
