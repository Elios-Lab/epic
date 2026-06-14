window.EPICAdmin = {
  methods: {
    selectedAdminContest() {
      if (!this.admin.expandedContestId) {
        return null;
      }
      return (
        this.admin.contests.find(
          (contest) => this.contestId(contest) === this.admin.expandedContestId
        ) || null
      );
    },
    async toggleAdminParticipants(contest) {
      const contestId = this.contestId(contest);
      if (this.admin.expandedContestId === contestId) {
        this.admin.expandedContestId = null;
        return;
      }
      this.admin.expandedContestId = contestId;
      this.admin.inviteEmails = "";
      await this.loadParticipants(contest);
    },
    async loadAdminDashboard() {
      if (this.admin.dashboardLoaded) {
        return;
      }
      this.admin.dashboardLoaded = true;
      await this.loadAdminOverview();
    },
    async setAdminTab(tab) {
      this.admin.tab = tab;
      this.admin.error = "";
      this.admin.success = "";
      if (tab !== "overview") this.stopMonitor();
      if (tab === "overview") {
        await this.loadAdminOverview();
      }
      if (tab === "users") {
        await this.loadAdminUsers();
      }
      if (tab === "organizerRequests") {
        await this.loadAdminOrganizerRequests();
      }
    },
    async loadAdminOverview() {
      this.admin.loadingOverview = true;
      this.admin.error = "";
      try {
        const [contestsResponse, usersResponse] = await Promise.all([
          this.apiRequest("/api/v1/contests?limit=1000"),
          this.apiRequest("/api/v1/users?limit=1000"),
        ]);
        this.admin.contests = contestsResponse.contests || [];
        this.admin.users = usersResponse.users || [];
        this.admin.totalUsers = usersResponse.total ?? this.admin.users.length;
      } catch (error) {
        this.admin.error = error.message || "Unable to load platform overview.";
      } finally {
        this.admin.loadingOverview = false;
      }
    },
    async loadAdminUsers() {
      this.admin.loadingUsers = true;
      this.admin.error = "";
      try {
        const response = await this.apiRequest("/api/v1/users?limit=1000");
        this.admin.users = response.users || [];
        this.admin.totalUsers = response.total ?? this.admin.users.length;
      } catch (error) {
        this.admin.error = error.message || "Unable to load users.";
      } finally {
        this.admin.loadingUsers = false;
      }
    },
    async loadAdminOrganizerRequests() {
      this.admin.loadingOrganizerRequests = true;
      this.admin.error = "";
      try {
        const status = this.admin.organizerRequestStatusFilter;
        const query =
          status === "ALL" ? "" : `?status=${encodeURIComponent(status)}`;
        const response = await this.apiRequest(
          `/api/v1/organizer-requests${query}`
        );
        this.admin.organizerRequests = response.requests || [];
        this.admin.totalOrganizerRequests =
          response.total ?? this.admin.organizerRequests.length;
      } catch (error) {
        this.admin.error = error.message || "Unable to load organizer requests.";
      } finally {
        this.admin.loadingOrganizerRequests = false;
      }
    },
    contestsByStatus() {
      return this.admin.contests.reduce((counts, contest) => {
        counts[contest.status] = (counts[contest.status] || 0) + 1;
        return counts;
      }, {});
    },
    sortAdminContests(key) {
      if (this.admin.contestSortKey === key) {
        this.admin.contestSortDirection =
          this.admin.contestSortDirection === "asc" ? "desc" : "asc";
      } else {
        this.admin.contestSortKey = key;
        this.admin.contestSortDirection = "asc";
      }
    },
    sortedAdminContests() {
      const key = this.admin.contestSortKey;
      const direction = this.admin.contestSortDirection === "asc" ? 1 : -1;
      return [...this.admin.contests].sort((left, right) => {
        const leftValue = left[key] ?? "";
        const rightValue = right[key] ?? "";
        if (typeof leftValue === "number" && typeof rightValue === "number") {
          return (leftValue - rightValue) * direction;
        }
        return String(leftValue).localeCompare(String(rightValue)) * direction;
      });
    },
    allowedStatusTransitions(status) {
      // Pause and resume are handled by dedicated PUT endpoints and
      // their own buttons, not via this transition selector.
      const transitions = {
        DRAFT: ["SCHEDULED", "ACTIVE"],
        SCHEDULED: ["ACTIVE"],
        ACTIVE: ["CLOSED"],
        PAUSED: ["CLOSED"],
        CLOSED: ["ARCHIVED"],
        ARCHIVED: [],
      };
      return transitions[status] || [];
    },
    async transitionAdminContest(contest, status) {
      if (!status) {
        return;
      }
      this.admin.error = "";
      this.admin.success = "";
      try {
        const contestId = this.contestId(contest);
        const updated = await this.apiRequest(`/api/v1/contests/${contestId}`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        });
        this.admin.contests = this.admin.contests.map((item) =>
          this.contestId(item) === this.contestId(updated) ? updated : item
        );
        this.admin.success = `Contest moved to ${status}.`;
      } catch (error) {
        this.admin.error = error.message || "Contest transition failed.";
      }
    },
    organizerRequestBadgeClass(status) {
      return window.EPICFormatters.organizerRequestBadgeClass(status);
    },
    async approveOrganizerRequest(request) {
      this.admin.error = "";
      this.admin.success = "";
      try {
        const updated = await this.apiRequest(
          `/api/v1/organizer-requests/${request.id}/approve`,
          { method: "POST" }
        );
        this.replaceOrganizerRequest(updated);
        this.admin.success = `Organizer request for ${request.email} approved.`;
        await this.loadAdminUsers();
      } catch (error) {
        this.admin.error = error.message || "Unable to approve organizer request.";
      }
    },
    async rejectOrganizerRequest(request) {
      this.admin.error = "";
      this.admin.success = "";
      try {
        const updated = await this.apiRequest(
          `/api/v1/organizer-requests/${request.id}/reject`,
          { method: "POST" }
        );
        this.replaceOrganizerRequest(updated);
        this.admin.success = `Organizer request for ${request.email} rejected.`;
      } catch (error) {
        this.admin.error = error.message || "Unable to reject organizer request.";
      }
    },
    replaceOrganizerRequest(updated) {
      this.admin.organizerRequests = this.admin.organizerRequests.map((request) =>
        request.id === updated.id ? updated : request
      );
    },
    filteredAdminUsers() {
      const query = this.admin.userSearch.trim().toLowerCase();
      if (!query) {
        return this.admin.users;
      }
      return this.admin.users.filter((account) =>
        `${account.username} ${account.email}`.toLowerCase().includes(query)
      );
    },
    async createUser() {
      this.admin.creatingUser = true;
      this.admin.error = "";
      this.admin.success = "";
      try {
        const created = await this.apiRequest("/api/v1/users", {
          method: "POST",
          body: JSON.stringify(this.admin.createUserForm),
        });
        this.admin.users = [created, ...this.admin.users];
        this.admin.totalUsers += 1;
        this.admin.success = `User '${created.username}' created successfully.`;
        this.admin.createUserForm = {
          username: "",
          email: "",
          password: "",
          role: "PARTICIPANT",
        };
        this.admin.showCreateUser = false;
      } catch (error) {
        this.admin.error = error.message || "User creation failed.";
      } finally {
        this.admin.creatingUser = false;
      }
    },
    async impersonate(account) {
      try {
        const data = await this.apiRequest(
          `/api/v1/users/${account.id}/impersonate`,
          { method: "POST" }
        );
        this.originalToken = this.token;
        this.token = data.access_token;
        window.EPICAuth.storeToken(this.token);
        const payload = this.decodeToken(this.token);
        this.user = {
          id: payload.sub,
          username: payload.username,
          role: payload.role,
        };
        this.impersonating = payload.username;
        this.state = "dashboard";
      } catch (error) {
        this.admin.error = error.message || "Impersonation failed.";
      }
    },
    stopImpersonating() {
      this.token = this.originalToken;
      this.originalToken = null;
      this.impersonating = null;
      window.EPICAuth.storeToken(this.token);
      const payload = this.decodeToken(this.token);
      this.user = {
        id: payload.sub,
        username: payload.username,
        role: payload.role,
      };
      this.state = "dashboard";
    },
    async updateUserRole(account, role) {
      if (role === account.role) {
        return;
      }
      this.admin.error = "";
      this.admin.success = "";
      try {
        const updated = await this.apiRequest(`/api/v1/users/${account.id}`, {
          method: "PATCH",
          body: JSON.stringify({ role }),
        });
        this.replaceAdminUser(updated);
        this.admin.success = "User role updated.";
      } catch (error) {
        this.admin.error = error.message || "User role update failed.";
      }
    },
    async toggleUserActive(account) {
      this.admin.error = "";
      this.admin.success = "";
      try {
        const updated = await this.apiRequest(`/api/v1/users/${account.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            status: account.is_active ? "SUSPENDED" : "ACTIVE",
          }),
        });
        this.replaceAdminUser(updated);
        this.admin.success = updated.is_active
          ? "User account activated."
          : "User account deactivated.";
      } catch (error) {
        this.admin.error = error.message || "User active status update failed.";
      }
    },
    replaceAdminUser(updated) {
      this.admin.users = this.admin.users.map((account) =>
        account.id === updated.id ? updated : account
      );
    },
  },
};
