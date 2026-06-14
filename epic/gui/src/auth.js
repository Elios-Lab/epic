export const auth = {
  notifyChanged() {
    window.dispatchEvent(new CustomEvent("epic-auth-changed"));
  },

  getToken() {
    return localStorage.getItem("epic_token");
  },

  storeToken(token) {
    localStorage.setItem("epic_token", token);
    this.notifyChanged();
  },

  clearToken() {
    localStorage.removeItem("epic_token");
    this.notifyChanged();
  },

  decodeToken(token) {
    try {
      const payload = token.split(".")[1];
      const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
      const json = decodeURIComponent(
        atob(base64)
          .split("")
          .map((char) => "%" + ("00" + char.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      );
      return JSON.parse(json);
    } catch (error) {
      return null;
    }
  },
};
