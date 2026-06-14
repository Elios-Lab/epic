window.EPICContestManagement = {
  methods: {
    async pauseContest(contest) {
      const cid = this.contestId(contest);
      const isOrganizer = this.user.role === "ORGANIZER";
      const ns = isOrganizer ? this.organizer : this.admin;
      ns.pausingContestId = cid;
      ns.error = "";
      ns.success = "";
      try {
        const updated = await this.apiRequest(`/api/v1/contests/${cid}/pause`, {
          method: "PUT",
        });
        if (isOrganizer) {
          this.replaceOrganizerContest(updated);
        } else {
          this.admin.contests = this.admin.contests.map((c) =>
            this.contestId(c) === cid ? updated : c
          );
        }
        ns.success = `Contest "${contest.name}" paused — simulation will stop within the next few steps.`;
      } catch (error) {
        ns.error = error.message || "Pause failed.";
      } finally {
        ns.pausingContestId = null;
      }
    },
    async resumeContest(contest) {
      const cid = this.contestId(contest);
      const isOrganizer = this.user.role === "ORGANIZER";
      const ns = isOrganizer ? this.organizer : this.admin;
      ns.pausingContestId = cid;
      ns.error = "";
      ns.success = "";
      try {
        const updated = await this.apiRequest(`/api/v1/contests/${cid}/resume`, {
          method: "PUT",
        });
        if (isOrganizer) {
          this.replaceOrganizerContest(updated);
        } else {
          this.admin.contests = this.admin.contests.map((c) =>
            this.contestId(c) === cid ? updated : c
          );
        }
        ns.success = `Contest "${contest.name}" resumed — simulation restarting.`;
      } catch (error) {
        ns.error = error.message || "Resume failed.";
      } finally {
        ns.pausingContestId = null;
      }
    },
    async deleteContest(contest) {
      const cid = this.contestId(contest);
      const confirmed = await new Promise((resolve) => {
        this.deleteModal.contestName = contest.name;
        this.deleteModal.confirm = () => {
          this.deleteModal.open = false;
          resolve(true);
        };
        this.deleteModal.cancel = () => {
          this.deleteModal.open = false;
          resolve(false);
        };
        this.deleteModal.open = true;
      });
      if (!confirmed) return;
      const isOrganizer = this.user.role === "ORGANIZER";
      const ns = isOrganizer ? this.organizer : this.admin;
      ns.deletingContestId = cid;
      ns.error = "";
      ns.success = "";
      try {
        await this.apiRequest(`/api/v1/contests/${cid}`, { method: "DELETE" });
        if (isOrganizer) {
          this.organizer.contests = this.organizer.contests.filter(
            (c) => this.contestId(c) !== cid
          );
        } else {
          this.admin.contests = this.admin.contests.filter(
            (c) => this.contestId(c) !== cid
          );
        }
        ns.success = `Contest "${contest.name}" deleted.`;
      } catch (error) {
        ns.error = error.message || "Delete failed.";
      } finally {
        ns.deletingContestId = null;
      }
    },
    participantManagerState() {
      return this.user.role === "ADMINISTRATOR" ? this.admin : this.organizer;
    },
    async loadParticipants(contest) {
      const contestId = this.contestId(contest);
      const ns = this.participantManagerState();
      ns.loadingParticipantsId = contestId;
      try {
        const [invitationsResponse, registrationsResponse] = await Promise.all([
          this.apiRequest(`/api/v1/contests/${contestId}/invitations`),
          this.apiRequest(`/api/v1/contest-registrations?contest_id=${contestId}`),
        ]);
        ns.invitations = {
          ...ns.invitations,
          [contestId]: invitationsResponse.invitations || [],
        };
        ns.registrations = {
          ...ns.registrations,
          [contestId]: registrationsResponse.registrations || [],
        };
      } catch (error) {
        ns.error = error.message || "Unable to load participants.";
      } finally {
        ns.loadingParticipantsId = null;
      }
    },
    async sendInvitations(contest) {
      const ns = this.participantManagerState();
      const emails = ns.inviteEmails
        .split(/[\s,;]+/)
        .map((email) => email.trim())
        .filter((email) => email.length > 0);
      if (emails.length === 0) {
        ns.error = "Enter at least one email address.";
        return;
      }
      ns.sendingInvites = true;
      ns.error = "";
      ns.success = "";
      try {
        const contestId = this.contestId(contest);
        const response = await this.apiRequest(
          `/api/v1/contests/${contestId}/invitations`,
          { method: "POST", body: JSON.stringify({ emails }) }
        );
        ns.success = `Sent ${response.created} invitation(s).`;
        ns.inviteEmails = "";
        await this.loadParticipants(contest);
      } catch (error) {
        ns.error = error.message || "Unable to send invitations.";
      } finally {
        ns.sendingInvites = false;
      }
    },
    async revokeInvitation(contest, invitation) {
      const ns = this.participantManagerState();
      ns.error = "";
      ns.success = "";
      try {
        const contestId = this.contestId(contest);
        await this.apiRequest(
          `/api/v1/contests/${contestId}/invitations/${invitation.id}`,
          { method: "DELETE" }
        );
        ns.success = `Invitation for ${invitation.email} revoked.`;
        await this.loadParticipants(contest);
      } catch (error) {
        ns.error = error.message || "Unable to revoke invitation.";
      }
    },
    async removeParticipant(contest, registration) {
      const ns = this.participantManagerState();
      ns.error = "";
      ns.success = "";
      try {
        await this.apiRequest(
          `/api/v1/contest-registrations/${registration.registration_id}`,
          { method: "DELETE" }
        );
        ns.success = `${registration.username || registration.email} removed from the contest.`;
        await this.loadParticipants(contest);
      } catch (error) {
        ns.error = error.message || "Unable to remove participant.";
      }
    },
  },
};
