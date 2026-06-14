window.EPICAuthFlow = {
  methods: {
    init() {
      // Invitation deep link: /register?token=... from the invitation email.
      if (window.location.pathname === "/register") {
        const inviteToken = new URLSearchParams(window.location.search).get(
          "token"
        );
        this.startRegistration(inviteToken || "");
        return;
      }
      const token = window.EPICAuth.getToken();
      if (!token) {
        return;
      }
      this.token = token;
      const payload = this.decodeToken(token);
      if (payload && payload.username && payload.role) {
        this.user = {
          id: payload.sub,
          username: payload.username,
          role: payload.role,
        };
        this.state = "dashboard";
      } else {
        this.logout();
      }
    },
    async startRegistration(inviteToken) {
      this.state = "register";
      this.registration.token = inviteToken;
      this.registration.error = "";
      if (!inviteToken) {
        this.registration.valid = false;
        this.registration.error = "This invitation link is missing its token.";
        return;
      }
      this.registration.checking = true;
      try {
        const response = await fetch(
          `/api/v1/invitations/${encodeURIComponent(inviteToken)}`
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.valid) {
          this.registration.valid = false;
          this.registration.error =
            "This invitation link is invalid, expired, or already used.";
          return;
        }
        this.registration.valid = true;
        this.registration.contestName = data.contest_name || "an EPIC contest";
        this.registration.email = data.email || "";
      } catch (error) {
        this.registration.valid = false;
        this.registration.error =
          "Could not verify the invitation. Please try again.";
      } finally {
        this.registration.checking = false;
      }
    },
    async acceptInvitation() {
      this.registration.error = "";
      if (
        this.registration.form.password !==
        this.registration.form.password_confirm
      ) {
        this.registration.error = "Passwords do not match.";
        return;
      }
      this.registration.submitting = true;
      try {
        const response = await fetch(
          `/api/v1/invitations/${encodeURIComponent(this.registration.token)}/accept`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              first_name: this.registration.form.first_name,
              last_name: this.registration.form.last_name,
              phone_number: this.registration.form.phone_number || null,
              password: this.registration.form.password,
            }),
          }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const message =
            data.error?.message ||
            data.detail?.error?.message ||
            "Registration failed. The invitation may have expired.";
          throw new Error(message);
        }
        this.token = data.access_token;
        window.EPICAuth.storeToken(this.token);
        const payload = this.decodeToken(this.token);
        this.user = {
          id: payload.sub,
          username: payload.username,
          role: payload.role,
        };
        this.registration.form.password = "";
        this.registration.form.password_confirm = "";
        window.history.replaceState({}, "", "/");
        this.state = "dashboard";
      } catch (error) {
        this.registration.error = error.message || "Registration failed.";
      } finally {
        this.registration.submitting = false;
      }
    },
    showLogin() {
      this.error = "";
      this.state = "login";
    },
    showOrganizerRequest() {
      this.error = "";
      this.organizerRequest.error = "";
      this.organizerRequest.success = "";
      this.state = "organizerRequest";
    },
    async submitOrganizerRequest() {
      this.organizerRequest.error = "";
      this.organizerRequest.success = "";
      if (
        this.organizerRequest.form.password !==
        this.organizerRequest.form.password_confirm
      ) {
        this.organizerRequest.error = "Passwords do not match.";
        return;
      }
      this.organizerRequest.submitting = true;
      try {
        const response = await fetch("/api/v1/organizer-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            first_name: this.organizerRequest.form.first_name,
            last_name: this.organizerRequest.form.last_name,
            email: this.organizerRequest.form.email,
            phone_number: this.organizerRequest.form.phone_number || null,
            password: this.organizerRequest.form.password,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(
            data.error?.message || "Organizer access request failed."
          );
        }
        this.organizerRequest.success =
          "Request submitted. An administrator will review it and notify you by email.";
        this.organizerRequest.form = {
          first_name: "",
          last_name: "",
          email: "",
          phone_number: "",
          password: "",
          password_confirm: "",
        };
      } catch (error) {
        this.organizerRequest.error =
          error.message || "Organizer access request failed.";
      } finally {
        this.organizerRequest.submitting = false;
      }
    },
    async login() {
      this.loading = true;
      this.error = "";
      try {
        const response = await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.credentials),
        });
        if (!response.ok) {
          throw new Error("Invalid username or password.");
        }
        const data = await response.json();
        this.token = data.access_token;
        window.EPICAuth.storeToken(this.token);
        const payload = this.decodeToken(this.token);
        this.user = {
          id: payload.sub,
          username: payload.username,
          role: payload.role,
        };
        this.credentials.password = "";
        this.state = "dashboard";
      } catch (error) {
        this.error = error.message || "Login failed.";
        window.EPICAuth.clearToken();
        this.token = null;
      } finally {
        this.loading = false;
      }
    },
    logout() {
      this.disconnectContest();
      window.EPICAuth.clearToken();
      this.token = null;
      this.user = { id: "", username: "", role: "" };
      this.credentials.password = "";
      this.error = "";
      this.state = "landing";
    },
  },
};
