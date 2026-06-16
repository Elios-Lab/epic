<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import Chart from "chart.js/auto";
import { api } from "../api.js";
import { formatters } from "../formatters.js";

const props = defineProps({
  token: { type: String, required: true },
  user: { type: Object, required: true },
});

const emit = defineEmits(["logout", "impersonate"]);

const tab = ref("overview");
const error = ref("");
const success = ref("");
const loadingOverview = ref(false);
const loadingUsers = ref(false);
const loadingOrganizerRequests = ref(false);
const loadingEnvironment = ref(false);
const loadingParticipantsId = ref(null);
const sendingInvites = ref(false);
const savingEnvironment = ref(false);
const restartingServer = ref(false);
const monitoredContest = ref(null);
const adminChartCanvas = ref(null);
const adminChart = ref(null);
const adminSocket = ref(null);
const adminLatest = reactive({ sequence_id: null, timestamp: "" });
const contests = ref([]);
const users = ref([]);
const organizerRequests = ref([]);
const environmentVariables = ref([]);
const environmentFile = ref("");
const totalUsers = ref(0);
const expandedContestId = ref(null);
const inviteEmails = ref("");
const invitations = ref({});
const registrations = ref({});
const userSearch = ref("");
const showCreateUser = ref(false);
const creatingUser = ref(false);
const organizerRequestStatusFilter = ref("PENDING");
const environmentForm = reactive({});

const createUserForm = reactive({
  username: "",
  email: "",
  password: "",
  role: "PARTICIPANT",
});

async function apiRequest(path, options = {}) {
  return api.request(props.token, path, options);
}

function contestId(contest) {
  return contest.contest_id || contest.id;
}

function formatDate(value) {
  return formatters.formatDate(value);
}

function statusBadgeClass(status) {
  return formatters.statusBadgeClass(status);
}

function roleBadgeClass(role) {
  return formatters.roleBadgeClass(role);
}

function organizerRequestBadgeClass(status) {
  return formatters.organizerRequestBadgeClass(status);
}

const activeContestCount = computed(
  () => contests.value.filter((contest) => contest.status === "ACTIVE").length
);

const filteredUsers = computed(() => {
  const query = userSearch.value.trim().toLowerCase();
  if (!query) return users.value;
  return users.value.filter((account) =>
    `${account.username} ${account.email}`.toLowerCase().includes(query)
  );
});

const environmentCategories = computed(() => {
  const groups = new Map();
  for (const variable of environmentVariables.value) {
    if (!groups.has(variable.category)) groups.set(variable.category, []);
    groups.get(variable.category).push(variable);
  }
  return Array.from(groups.entries()).map(([category, variables]) => ({
    category,
    variables,
  }));
});

function selectedContest() {
  return (
    contests.value.find((contest) => contestId(contest) === expandedContestId.value) ||
    null
  );
}

function allowedStatusTransitions(status) {
  const transitions = {
    DRAFT: ["SCHEDULED", "ACTIVE"],
    SCHEDULED: ["ACTIVE"],
    ACTIVE: ["CLOSED"],
    PAUSED: ["CLOSED"],
    CLOSED: ["ARCHIVED"],
    ARCHIVED: [],
  };
  return transitions[status] || [];
}

function replaceContest(updated) {
  contests.value = contests.value.map((contest) =>
    contestId(contest) === contestId(updated) ? updated : contest
  );
}

function replaceUser(updated) {
  users.value = users.value.map((account) =>
    account.id === updated.id ? updated : account
  );
}

function replaceOrganizerRequest(updated) {
  organizerRequests.value = organizerRequests.value.map((request) =>
    request.id === updated.id ? updated : request
  );
}

async function setTab(nextTab) {
  tab.value = nextTab;
  error.value = "";
  success.value = "";
  if (nextTab === "overview") await loadOverview();
  if (nextTab === "users") await loadUsers();
  if (nextTab === "organizerRequests") await loadOrganizerRequests();
  if (nextTab === "environment") await loadEnvironment();
}

async function loadOverview() {
  loadingOverview.value = true;
  error.value = "";
  try {
    const [contestResponse, userResponse] = await Promise.all([
      apiRequest("/api/v1/contests?limit=1000"),
      apiRequest("/api/v1/users?limit=1000"),
    ]);
    contests.value = contestResponse.contests || [];
    users.value = userResponse.users || [];
    totalUsers.value = userResponse.total ?? users.value.length;
  } catch (loadError) {
    error.value = loadError.message || "Unable to load platform overview.";
  } finally {
    loadingOverview.value = false;
  }
}

async function loadUsers() {
  loadingUsers.value = true;
  error.value = "";
  try {
    const response = await apiRequest("/api/v1/users?limit=1000");
    users.value = response.users || [];
    totalUsers.value = response.total ?? users.value.length;
  } catch (loadError) {
    error.value = loadError.message || "Unable to load users.";
  } finally {
    loadingUsers.value = false;
  }
}

async function loadOrganizerRequests() {
  loadingOrganizerRequests.value = true;
  error.value = "";
  try {
    const status = organizerRequestStatusFilter.value;
    const query = status === "ALL" ? "" : `?status=${encodeURIComponent(status)}`;
    const response = await apiRequest(`/api/v1/organizer-requests${query}`);
    organizerRequests.value = response.requests || [];
  } catch (loadError) {
    error.value = loadError.message || "Unable to load organizer requests.";
  } finally {
    loadingOrganizerRequests.value = false;
  }
}

async function loadEnvironment() {
  loadingEnvironment.value = true;
  error.value = "";
  try {
    const response = await apiRequest("/api/v1/admin/environment");
    environmentFile.value = response.env_file;
    environmentVariables.value = response.variables || [];
    for (const variable of environmentVariables.value) {
      environmentForm[variable.key] = variable.is_secret ? "" : (variable.value ?? "");
    }
  } catch (loadError) {
    error.value = loadError.message || "Unable to load environment settings.";
  } finally {
    loadingEnvironment.value = false;
  }
}

async function saveEnvironment() {
  savingEnvironment.value = true;
  error.value = "";
  success.value = "";
  const values = {};
  for (const variable of environmentVariables.value) {
    const value = environmentForm[variable.key] ?? "";
    if (variable.is_secret && value === "" && variable.is_set) {
      continue;
    }
    values[variable.key] = value === "" ? null : value;
  }
  try {
    const response = await apiRequest("/api/v1/admin/environment", {
      method: "PUT",
      body: JSON.stringify({ values }),
    });
    environmentFile.value = response.env_file;
    environmentVariables.value = response.variables || [];
    for (const variable of environmentVariables.value) {
      environmentForm[variable.key] = variable.is_secret ? "" : (variable.value ?? "");
    }
    success.value = "Environment file updated. Restart the server to apply changes.";
  } catch (saveError) {
    error.value = saveError.message || "Unable to update environment settings.";
  } finally {
    savingEnvironment.value = false;
  }
}

async function restartServer() {
  if (!confirm("Restart the server now? It will be briefly unavailable while it restarts.")) return;
  restartingServer.value = true;
  error.value = "";
  success.value = "";
  try {
    await apiRequest("/api/v1/admin/environment/restart", { method: "POST" });
    success.value = "Restart signal sent. The server will be back in a few seconds.";
  } catch {
    error.value = "Failed to send restart signal.";
  } finally {
    restartingServer.value = false;
  }
}

function createAdminChart() {
  const canvas = adminChartCanvas.value;
  if (!canvas) return;
  adminChart.value = new Chart(canvas, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "nearest" },
      scales: {
        x: { ticks: { color: "#475569", maxTicksLimit: 10 }, grid: { color: "#e2e8f0" } },
        y: { ticks: { color: "#475569" }, grid: { color: "#e2e8f0" } },
      },
      plugins: { legend: { labels: { color: "#0f172a" } } },
    },
  });
}

function appendAdminObservation(observation) {
  if (!adminChart.value) return;
  const sensors = observation.sensors || {};
  const colors = ["#0d3b6e", "#0096c7", "#14b8a6", "#6366f1", "#f97316", "#64748b"];
  for (const sensorId of Object.keys(sensors)) {
    if (!adminChart.value.data.datasets.some((d) => d.label === sensorId)) {
      const color = colors[adminChart.value.data.datasets.length % colors.length];
      adminChart.value.data.datasets.push({
        label: sensorId, data: [], borderColor: color, backgroundColor: color,
        borderWidth: 2, pointRadius: 0, tension: 0.25,
      });
    }
  }
  adminChart.value.data.labels.push(observation.sequence_id);
  for (const dataset of adminChart.value.data.datasets) {
    dataset.data.push(sensors[dataset.label] ?? null);
    if (dataset.data.length > 100) dataset.data.shift();
  }
  if (adminChart.value.data.labels.length > 100) adminChart.value.data.labels.shift();
  adminChart.value.update("none");
}

function closeAdminMonitor() {
  if (adminSocket.value) { adminSocket.value.close(); adminSocket.value = null; }
  if (adminChart.value) { adminChart.value.destroy(); adminChart.value = null; }
  monitoredContest.value = null;
}

async function openAdminMonitor(contest) {
  closeAdminMonitor();
  monitoredContest.value = contest;
  adminLatest.sequence_id = null;
  adminLatest.timestamp = "";
  await nextTick();
  createAdminChart();
  const id = contestId(contest);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${window.location.host}/api/v1/ws/contests/${id}?token=${encodeURIComponent(props.token)}`;
  adminSocket.value = new WebSocket(url);
  adminSocket.value.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.sensors) {
      adminLatest.sequence_id = msg.sequence_id;
      adminLatest.timestamp = msg.timestamp;
      appendAdminObservation(msg);
    }
  };
  adminSocket.value.onerror = () => { error.value = "Monitor stream connection failed."; };
  adminSocket.value.onclose = () => {
    if (monitoredContest.value) error.value = "Monitor stream disconnected.";
  };
}

async function transitionContest(contest, status) {
  if (!status) return;
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/contests/${contestId(contest)}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    replaceContest(updated);
    success.value = `Contest moved to ${status}.`;
  } catch (transitionError) {
    error.value = transitionError.message || "Contest transition failed.";
  }
}

async function toggleParticipants(contest) {
  const id = contestId(contest);
  if (expandedContestId.value === id) {
    expandedContestId.value = null;
    return;
  }
  expandedContestId.value = id;
  inviteEmails.value = "";
  await loadParticipants(contest);
}

async function loadParticipants(contest) {
  const id = contestId(contest);
  loadingParticipantsId.value = id;
  try {
    const [invitationResponse, registrationResponse] = await Promise.all([
      apiRequest(`/api/v1/contests/${id}/invitations`),
      apiRequest(`/api/v1/contest-registrations?contest_id=${id}`),
    ]);
    invitations.value = { ...invitations.value, [id]: invitationResponse.invitations || [] };
    registrations.value = {
      ...registrations.value,
      [id]: registrationResponse.registrations || [],
    };
  } catch (participantsError) {
    error.value = participantsError.message || "Unable to load participants.";
  } finally {
    loadingParticipantsId.value = null;
  }
}

async function sendInvitations() {
  const contest = selectedContest();
  if (!contest) return;
  const emails = inviteEmails.value
    .split(/[\s,;]+/)
    .map((email) => email.trim())
    .filter(Boolean);
  if (emails.length === 0) {
    error.value = "Enter at least one email address.";
    return;
  }
  sendingInvites.value = true;
  error.value = "";
  success.value = "";
  try {
    const response = await apiRequest(`/api/v1/contests/${contestId(contest)}/invitations`, {
      method: "POST",
      body: JSON.stringify({ emails }),
    });
    success.value = `Sent ${response.created} invitation(s).`;
    inviteEmails.value = "";
    await loadParticipants(contest);
  } catch (inviteError) {
    error.value = inviteError.message || "Unable to send invitations.";
  } finally {
    sendingInvites.value = false;
  }
}

async function removeParticipant(registration) {
  const contest = selectedContest();
  if (!contest) return;
  error.value = "";
  success.value = "";
  try {
    await apiRequest(`/api/v1/contest-registrations/${registration.registration_id}`, {
      method: "DELETE",
    });
    success.value = `${registration.username || registration.email} removed from the contest.`;
    await loadParticipants(contest);
  } catch (removeError) {
    error.value = removeError.message || "Unable to remove participant.";
  }
}

async function approveOrganizerRequest(request) {
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/organizer-requests/${request.id}/approve`, {
      method: "POST",
    });
    replaceOrganizerRequest(updated);
    success.value = `Organizer request for ${request.email} approved.`;
    await loadUsers();
  } catch (approveError) {
    error.value = approveError.message || "Unable to approve organizer request.";
  }
}

async function rejectOrganizerRequest(request) {
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/organizer-requests/${request.id}/reject`, {
      method: "POST",
    });
    replaceOrganizerRequest(updated);
    success.value = `Organizer request for ${request.email} rejected.`;
  } catch (rejectError) {
    error.value = rejectError.message || "Unable to reject organizer request.";
  }
}

async function createUser() {
  creatingUser.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await apiRequest("/api/v1/users", {
      method: "POST",
      body: JSON.stringify(createUserForm),
    });
    users.value = [created, ...users.value];
    totalUsers.value += 1;
    success.value = `User '${created.username}' created successfully.`;
    Object.assign(createUserForm, {
      username: "",
      email: "",
      password: "",
      role: "PARTICIPANT",
    });
    showCreateUser.value = false;
  } catch (createError) {
    error.value = createError.message || "User creation failed.";
  } finally {
    creatingUser.value = false;
  }
}

async function toggleUserActive(account) {
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/users/${account.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: account.is_active ? "SUSPENDED" : "ACTIVE",
      }),
    });
    replaceUser(updated);
    success.value = updated.is_active
      ? "User account activated."
      : "User account deactivated.";
  } catch (toggleError) {
    error.value = toggleError.message || "User active status update failed.";
  }
}

async function impersonate(account) {
  error.value = "";
  try {
    const data = await apiRequest(`/api/v1/users/${account.id}/impersonate`, {
      method: "POST",
    });
    emit("impersonate", { token: data.access_token, username: account.username });
  } catch (impersonateError) {
    error.value = impersonateError.message || "Impersonation failed.";
  }
}

onMounted(() => {
  loadOverview();
});

onBeforeUnmount(() => {
  closeAdminMonitor();
});
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-slate-900">
    <nav class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div>
          <div class="text-lg font-semibold text-epic-deep">EPIC</div>
          <div class="text-xs font-medium uppercase tracking-wide text-epic-cyan">Administrator</div>
        </div>
        <div class="flex items-center gap-3">
          <span class="max-w-[12rem] truncate text-sm font-medium text-slate-700">{{ user.username }}</span>
          <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="emit('logout')">
            Logout
          </button>
        </div>
      </div>
    </nav>

    <section class="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div class="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <div class="space-y-6">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 class="text-3xl font-semibold text-epic-deep">Administrator Dashboard</h1>
              <p class="mt-2 text-slate-600">Monitor platform activity and manage users.</p>
            </div>
            <div class="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
              <button type="button" :class="tab === 'overview' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('overview')">
                Platform Overview
              </button>
              <button type="button" :class="tab === 'users' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('users')">
                Users
              </button>
              <button type="button" :class="tab === 'organizerRequests' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('organizerRequests')">
                Organizer Requests
              </button>
              <button type="button" :class="tab === 'environment' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('environment')">
                Settings
              </button>
            </div>
          </div>

          <p v-if="error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="success" class="rounded-md bg-cyan-50 px-4 py-3 text-sm text-epic-navy">{{ success }}</p>

          <div v-if="tab === 'overview'" class="space-y-6">
            <div class="flex items-center justify-between gap-4">
              <h2 class="text-xl font-semibold text-slate-900">Platform Overview</h2>
              <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="loadOverview">
                Refresh
              </button>
            </div>
            <p v-if="loadingOverview" class="text-sm text-slate-500">Loading platform overview...</p>
            <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div class="rounded-md border border-slate-200 bg-slate-50 p-5">
                <div class="text-sm font-medium uppercase tracking-wide text-slate-500">Total contests</div>
                <div class="mt-2 text-3xl font-semibold text-epic-deep">{{ contests.length }}</div>
              </div>
              <div class="rounded-md border border-slate-200 bg-slate-50 p-5">
                <div class="text-sm font-medium uppercase tracking-wide text-slate-500">Active contests</div>
                <div class="mt-2 text-3xl font-semibold text-emerald-700">{{ activeContestCount }}</div>
              </div>
              <div class="rounded-md border border-slate-200 bg-slate-50 p-5">
                <div class="text-sm font-medium uppercase tracking-wide text-slate-500">Registered users</div>
                <div class="mt-2 text-3xl font-semibold text-epic-deep">{{ totalUsers }}</div>
              </div>
            </div>

            <div class="overflow-x-auto rounded-md border border-slate-200">
              <table class="min-w-full divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50">
                  <tr class="text-left text-slate-500">
                    <th class="px-4 py-3 font-semibold">Name</th>
                    <th class="px-4 py-3 font-semibold">Status</th>
                    <th class="px-4 py-3 font-semibold">Start</th>
                    <th class="px-4 py-3 font-semibold">End</th>
                    <th class="px-4 py-3 font-semibold">Transition</th>
                    <th class="px-4 py-3 font-semibold">Participants</th>
                    <th class="px-4 py-3 font-semibold">Monitor</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-200 bg-white">
                  <tr v-for="contest in contests" :key="contestId(contest)">
                    <td class="px-4 py-3 font-medium text-slate-900">{{ contest.name }}</td>
                    <td class="px-4 py-3"><span :class="statusBadgeClass(contest.status)" class="rounded-full px-2.5 py-1 text-xs font-semibold">{{ contest.status }}</span></td>
                    <td class="px-4 py-3 text-slate-600">{{ formatDate(contest.start_date) }}</td>
                    <td class="px-4 py-3 text-slate-600">{{ formatDate(contest.end_date) }}</td>
                    <td class="px-4 py-3">
                      <select class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" @change="transitionContest(contest, $event.target.value); $event.target.value = ''">
                        <option value="">Choose</option>
                        <option v-for="status in allowedStatusTransitions(contest.status)" :key="status" :value="status">{{ status }}</option>
                      </select>
                    </td>
                    <td class="px-4 py-3">
                      <button type="button" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="toggleParticipants(contest)">
                        {{ expandedContestId === contestId(contest) ? "Hide" : "Participants" }}
                      </button>
                    </td>
                    <td class="px-4 py-3">
                      <button v-if="contest.status === 'ACTIVE'" type="button" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="monitoredContest && contestId(monitoredContest) === contestId(contest) ? closeAdminMonitor() : openAdminMonitor(contest)">
                        {{ monitoredContest && contestId(monitoredContest) === contestId(contest) ? "Close" : "Monitor" }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="monitoredContest" class="rounded-md border border-slate-200 bg-white p-5 space-y-4">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-base font-semibold text-slate-900">Live monitor — {{ monitoredContest.name }}</h3>
                  <p class="text-sm text-slate-500">Real-time sensor stream from {{ monitoredContest.twin_id }}.</p>
                </div>
                <button type="button" class="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="closeAdminMonitor">Close</button>
              </div>
              <div class="rounded-md border border-slate-200 bg-slate-50 p-4">
                <div class="h-64">
                  <canvas ref="adminChartCanvas" class="h-full w-full"></canvas>
                </div>
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div class="rounded-md bg-slate-50 p-4">
                  <div class="text-sm font-medium text-slate-500">Latest sequence</div>
                  <div class="mt-1 text-2xl font-semibold text-epic-deep">{{ adminLatest.sequence_id ?? "—" }}</div>
                </div>
                <div class="rounded-md bg-slate-50 p-4">
                  <div class="text-sm font-medium text-slate-500">Latest timestamp</div>
                  <div class="mt-1 text-lg font-semibold text-epic-deep">{{ adminLatest.timestamp || "—" }}</div>
                </div>
              </div>
            </div>

            <div v-if="expandedContestId && selectedContest()" data-testid="admin-participants-panel" class="rounded-md border border-slate-200 bg-white p-5">
              <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 class="text-base font-semibold text-slate-900">Participants for {{ selectedContest().name }}</h3>
                  <p class="text-sm text-slate-500">Invite new participants, review who joined, and remove access when needed.</p>
                </div>
                <span v-if="loadingParticipantsId === expandedContestId" class="text-sm text-slate-500">Loading...</span>
              </div>

              <form class="mb-5 rounded-md border border-cyan-100 bg-cyan-50 p-4" @submit.prevent="sendInvitations">
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">Send registration invitation emails</span>
                  <textarea v-model="inviteEmails" rows="2" placeholder="anna@example.com, marco@example.com - separate with commas, spaces, or new lines" class="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"></textarea>
                </label>
                <button type="submit" :disabled="sendingInvites" class="mt-2 rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep disabled:opacity-60">
                  {{ sendingInvites ? "Sending..." : "Send invitations" }}
                </button>
              </form>

              <div class="grid gap-5 xl:grid-cols-2">
                <div>
                  <h4 class="mb-2 text-sm font-semibold text-slate-700">Invited</h4>
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <tbody class="divide-y divide-slate-200">
                      <tr v-for="invitation in invitations[expandedContestId] || []" :key="invitation.id">
                        <td class="px-3 py-2">{{ invitation.email }}</td>
                        <td class="px-3 py-2"><span :class="invitation.used ? 'rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800' : 'rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800'">{{ invitation.used ? "Accepted" : "Pending" }}</span></td>
                      </tr>
                      <tr v-if="(invitations[expandedContestId] || []).length === 0"><td colspan="2" class="px-3 py-3 text-slate-500">No invitations sent yet.</td></tr>
                    </tbody>
                  </table>
                </div>
                <div>
                  <h4 class="mb-2 text-sm font-semibold text-slate-700">Registered</h4>
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <tbody class="divide-y divide-slate-200">
                      <tr v-for="registration in registrations[expandedContestId] || []" :key="registration.registration_id">
                        <td class="px-3 py-2">{{ registration.username }}</td>
                        <td class="px-3 py-2">{{ registration.email }}</td>
                        <td class="px-3 py-2">{{ registration.status }}</td>
                        <td class="px-3 py-2 text-right"><button v-if="registration.status === 'REGISTERED'" type="button" class="text-xs font-semibold text-red-600 hover:text-red-800" @click="removeParticipant(registration)">Remove</button></td>
                      </tr>
                      <tr v-if="(registrations[expandedContestId] || []).length === 0"><td colspan="4" class="px-3 py-3 text-slate-500">No registered participants yet.</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <div v-if="tab === 'users'" class="space-y-5">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <h2 class="text-xl font-semibold text-slate-900">Users</h2>
              <div class="flex flex-col gap-3 sm:flex-row">
                <input v-model="userSearch" type="search" placeholder="Search username or email" class="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
                <button type="button" class="rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep" @click="showCreateUser = !showCreateUser">New User</button>
                <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="loadUsers">Refresh</button>
              </div>
            </div>
            <form v-if="showCreateUser" class="space-y-4 rounded-md border border-cyan-200 bg-cyan-50 p-5" @submit.prevent="createUser">
              <h3 class="text-base font-semibold text-slate-900">New User</h3>
              <div class="grid gap-4 sm:grid-cols-2">
                <label class="block"><span class="text-sm font-medium text-slate-700">Username</span><input v-model="createUserForm.username" type="text" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" /></label>
                <label class="block"><span class="text-sm font-medium text-slate-700">Email</span><input v-model="createUserForm.email" type="email" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" /></label>
                <label class="block"><span class="text-sm font-medium text-slate-700">Password</span><input v-model="createUserForm.password" type="password" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" /></label>
                <label class="block"><span class="text-sm font-medium text-slate-700">Role</span><select v-model="createUserForm.role" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"><option value="PARTICIPANT">PARTICIPANT</option><option value="ORGANIZER">ORGANIZER</option><option value="ADMINISTRATOR">ADMINISTRATOR</option></select></label>
              </div>
              <button type="submit" :disabled="creatingUser" class="rounded-md bg-epic-navy px-5 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep disabled:opacity-60">{{ creatingUser ? "Creating..." : "Create" }}</button>
            </form>
            <p v-if="loadingUsers" class="text-sm text-slate-500">Loading users...</p>
            <div class="overflow-x-auto rounded-md border border-slate-200">
              <table class="min-w-full divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50"><tr class="text-left text-slate-500"><th class="px-4 py-3 font-semibold">Username</th><th class="px-4 py-3 font-semibold">Email</th><th class="px-4 py-3 font-semibold">Role</th><th class="px-4 py-3 font-semibold">Active</th><th class="px-4 py-3 font-semibold">Actions</th></tr></thead>
                <tbody class="divide-y divide-slate-200 bg-white">
                  <tr v-for="account in filteredUsers" :key="account.id">
                    <td class="px-4 py-3 font-medium text-slate-900">{{ account.username }}</td>
                    <td class="px-4 py-3 text-slate-600">{{ account.email }}</td>
                    <td class="px-4 py-3"><span :class="roleBadgeClass(account.role)" class="rounded-full px-2.5 py-1 text-xs font-semibold">{{ account.role }}</span></td>
                    <td class="px-4 py-3"><span :class="account.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'" class="rounded-full px-2.5 py-1 text-xs font-semibold">{{ account.is_active ? "Active" : "Inactive" }}</span></td>
                    <td class="px-4 py-3">
                      <div class="flex flex-wrap gap-2">
                        <button type="button" class="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="toggleUserActive(account)">{{ account.is_active ? "Deactivate" : "Activate" }}</button>
                        <button v-if="account.id !== user.id" type="button" class="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="impersonate(account)">Impersonate</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="tab === 'organizerRequests'" class="space-y-5">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 class="text-xl font-semibold text-slate-900">Organizer Requests</h2>
                <p class="mt-1 text-sm text-slate-600">Review people who asked to create and manage contests.</p>
              </div>
              <select v-model="organizerRequestStatusFilter" class="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" @change="loadOrganizerRequests">
                <option value="PENDING">PENDING</option>
                <option value="APPROVED">APPROVED</option>
                <option value="REJECTED">REJECTED</option>
                <option value="ALL">ALL</option>
              </select>
            </div>
            <p v-if="loadingOrganizerRequests" class="text-sm text-slate-500">Loading organizer requests...</p>
            <div class="overflow-x-auto rounded-md border border-slate-200">
              <table class="min-w-full divide-y divide-slate-200 text-sm">
                <thead class="bg-slate-50"><tr class="text-left text-slate-500"><th class="px-4 py-3 font-semibold">Name</th><th class="px-4 py-3 font-semibold">Email</th><th class="px-4 py-3 font-semibold">Status</th><th class="px-4 py-3 font-semibold">Actions</th></tr></thead>
                <tbody class="divide-y divide-slate-200 bg-white">
                  <tr v-for="request in organizerRequests" :key="request.id">
                    <td class="px-4 py-3 font-medium text-slate-900">{{ request.first_name }} {{ request.last_name }}</td>
                    <td class="px-4 py-3 text-slate-600">{{ request.email }}</td>
                    <td class="px-4 py-3"><span :class="organizerRequestBadgeClass(request.status)" class="rounded-full px-2.5 py-1 text-xs font-semibold">{{ request.status }}</span></td>
                    <td class="px-4 py-3">
                      <div class="flex flex-wrap gap-2">
                        <button v-if="request.status === 'PENDING'" type="button" class="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700" @click="approveOrganizerRequest(request)">Approve</button>
                        <button v-if="request.status === 'PENDING'" type="button" class="rounded-md border border-red-300 px-3 py-2 text-sm font-semibold text-red-600 transition hover:border-red-500 hover:bg-red-50" @click="rejectOrganizerRequest(request)">Reject</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="organizerRequests.length === 0"><td colspan="4" class="px-4 py-6 text-center text-slate-500">No organizer requests match the current filter.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="tab === 'environment'" class="space-y-5">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 class="text-xl font-semibold text-slate-900">Environment Settings</h2>
                <p class="mt-1 text-sm text-slate-600">
                  Edit supported `.env` variables. Secret values are hidden; enter a new value only when replacing them.
                </p>
                <p v-if="environmentFile" class="mt-1 font-mono text-xs text-slate-500">{{ environmentFile }}</p>
              </div>
              <div class="flex gap-2">
                <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="loadEnvironment">
                  Refresh
                </button>
                <button type="button" :disabled="savingEnvironment" class="rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep disabled:opacity-60" @click="saveEnvironment">
                  {{ savingEnvironment ? "Saving..." : "Save settings" }}
                </button>
                <button type="button" :disabled="restartingServer" class="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60" @click="restartServer">
                  {{ restartingServer ? "Restarting..." : "Restart server" }}
                </button>
              </div>
            </div>

            <p class="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              Changes are written to the environment file but are not applied to the running process until the server restarts.
            </p>
            <p v-if="loadingEnvironment" class="text-sm text-slate-500">Loading environment settings...</p>

            <div v-for="group in environmentCategories" :key="group.category" class="rounded-md border border-slate-200 bg-white">
              <div class="border-b border-slate-200 bg-slate-50 px-4 py-3">
                <h3 class="text-sm font-semibold text-slate-900">{{ group.category }}</h3>
              </div>
              <div class="divide-y divide-slate-100">
                <label v-for="variable in group.variables" :key="variable.key" class="grid gap-3 px-4 py-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
                  <div>
                    <div class="font-mono text-sm font-semibold text-slate-900">
                      {{ variable.key }}<span v-if="variable.is_required" class="text-red-600">*</span>
                    </div>
                    <div class="mt-1 text-xs leading-5 text-slate-500">{{ variable.description }}</div>
                    <div v-if="variable.is_secret && variable.is_set" class="mt-1 text-xs font-medium text-emerald-700">Secret is configured</div>
                  </div>
                  <input
                    v-model="environmentForm[variable.key]"
                    :type="variable.is_secret ? 'password' : 'text'"
                    :placeholder="variable.is_secret && variable.is_set ? 'Leave blank to keep existing value' : ''"
                    class="w-full rounded-md border border-slate-300 px-4 py-2 font-mono text-sm text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
