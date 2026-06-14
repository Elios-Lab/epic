function epicApp() {
  return {
    ...window.EPICState.create(),
    async apiRequest(path, options = {}) {
      return window.EPICApi.request(this.token, path, options);
    },
    ...window.EPICAuthFlow.methods,
    ...window.EPICMonitor.methods,
    ...window.EPICContestManagement.methods,
    ...window.EPICParticipant.methods,
    ...window.EPICOrganizer.methods,
    ...window.EPICAdmin.methods,
    contestId(contest) {
      return contest.contest_id || contest.id;
    },
    formatDate(value) {
      return window.EPICFormatters.formatDate(value);
    },
    formatScore(value) {
      return window.EPICFormatters.formatScore(value);
    },
    contestPhaseLabel(contest) {
      return window.EPICFormatters.contestPhaseLabel(contest);
    },
    contestPhaseClass(contest) {
      return window.EPICFormatters.contestPhaseClass(contest);
    },
    statusBadgeClass(status) {
      return window.EPICFormatters.statusBadgeClass(status);
    },
    roleBadgeClass(role) {
      return window.EPICFormatters.roleBadgeClass(role);
    },
    toLocalDateTime(value) {
      return window.EPICFormatters.toLocalDateTime(value);
    },
    toApiDateTime(value) {
      return window.EPICFormatters.toApiDateTime(value);
    },
    decodeToken(token) {
      return window.EPICAuth.decodeToken(token);
    },
  };
}
