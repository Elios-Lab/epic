window.EPICFormatters = {
  formatDate(value) {
    if (!value) {
      return "-";
    }
    return new Date(value).toLocaleString();
  },

  formatScore(value) {
    if (value === null || value === undefined) {
      return "-";
    }
    return Number(value).toFixed(4);
  },

  contestPhaseLabel(contest) {
    if (!contest.end_of_observation) return "";
    const now = Date.now();
    const obsEnd = new Date(contest.end_of_observation).getTime();
    const evalEnd = obsEnd + (contest.prediction_horizon_seconds || 0) * 1000;
    if (now < obsEnd) return "Observation";
    if (now < evalEnd) return "Evaluation";
    return "Submission open";
  },

  contestPhaseClass(contest) {
    if (!contest.end_of_observation) return "";
    const now = Date.now();
    const obsEnd = new Date(contest.end_of_observation).getTime();
    const evalEnd = obsEnd + (contest.prediction_horizon_seconds || 0) * 1000;
    if (now < obsEnd) return "bg-cyan-100 text-cyan-800";
    if (now < evalEnd) return "bg-purple-100 text-purple-800";
    return "bg-emerald-100 text-emerald-800";
  },

  statusBadgeClass(status) {
    const classes = {
      ACTIVE: "bg-emerald-100 text-emerald-800",
      SCHEDULED: "bg-yellow-100 text-yellow-800",
      DRAFT: "bg-slate-200 text-slate-700",
      PAUSED: "bg-amber-100 text-amber-800",
      CLOSED: "bg-red-100 text-red-800",
      ARCHIVED: "bg-slate-300 text-slate-700",
    };
    return classes[status] || "bg-slate-200 text-slate-700";
  },

  roleBadgeClass(role) {
    const classes = {
      ADMINISTRATOR: "bg-blue-100 text-blue-800",
      ORGANIZER: "bg-emerald-100 text-emerald-800",
      PARTICIPANT: "bg-slate-200 text-slate-700",
    };
    return classes[role] || "bg-slate-200 text-slate-700";
  },

  organizerRequestBadgeClass(status) {
    const classes = {
      PENDING: "bg-amber-100 text-amber-800",
      APPROVED: "bg-emerald-100 text-emerald-800",
      REJECTED: "bg-red-100 text-red-800",
    };
    return classes[status] || "bg-slate-200 text-slate-700";
  },

  toLocalDateTime(value) {
    if (!value) {
      return "";
    }
    const date = new Date(value);
    const offsetMs = date.getTimezoneOffset() * 60000;
    return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
  },

  toApiDateTime(value) {
    return new Date(value).toISOString();
  },
};
