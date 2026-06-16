<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { api } from "../api.js";
import { auth } from "../auth.js";
import { formatters } from "../formatters.js";

const props = defineProps({
  token: { type: String, required: true },
  user: { type: Object, required: true },
});

const emit = defineEmits(["logout"]);

const tab = ref("contests");
const error = ref("");
const success = ref("");
const loadingContests = ref(false);
const loadingTemplates = ref(false);
const loadingCatalog = ref(false);
const loadingParticipantsId = ref(null);
const loadingLeaderboardId = ref(null);
const creating = ref(false);
const pausingContestId = ref(null);
const deletingContestId = ref(null);
const contests = ref([]);
const templates = ref([]);
const selectedTemplate = ref(null);
const catalogProfile = ref(null);
const newStep = ref(1);
const expandedContestId = ref(null);
const inviteEmails = ref("");
const sendingInvites = ref(false);
const invitations = ref({});
const registrations = ref({});
const leaderboards = ref({});
const deleteModal = reactive({ open: false, contest: null });

const monitor = reactive({
  contest: null,
  error: "",
});

const monitorChartCanvas = ref(null);
let monitorSocket = null;
let monitorChart = null;
let monitorReady = false;
let monitorBuffer = [];

const form = reactive(defaultForm());

function defaultForm() {
  return {
    name: "",
    description: "",
    visibility: "PUBLIC",
    start_date: "",
    end_date: "",
    sampling_rate_hz: 1,
    twin_id: "",
    sensor_selections: [],
    fault_entries: [],
    initial_conditions: null,
    task_type: "FORECASTING",
    metric_ids: ["mae"],
    score_against: "ground_truth",
    target_variables: [],
    observation_horizon_days: 2,
    prediction_horizon_seconds: 3600,
  };
}

async function apiRequest(path, options = {}) {
  return api.request(props.token, path, options);
}

function contestId(contest) {
  return contest.contest_id || contest.id;
}

function formatDate(value) {
  return formatters.formatDate(value);
}

function formatScore(value) {
  return formatters.formatScore(value);
}

function statusBadgeClass(status) {
  return formatters.statusBadgeClass(status);
}

function contestPhaseLabel(contest) {
  return formatters.contestPhaseLabel(contest);
}

function contestPhaseClass(contest) {
  return formatters.contestPhaseClass(contest);
}

function toLocalDateTime(value) {
  return formatters.toLocalDateTime(value);
}

function toApiDateTime(value) {
  return formatters.toApiDateTime(value);
}

function replaceContest(updated) {
  const id = contestId(updated);
  contests.value = contests.value.map((contest) =>
    contestId(contest) === id ? updated : contest
  );
}

async function setTab(nextTab) {
  tab.value = nextTab;
  error.value = "";
  success.value = "";
  if (nextTab !== "contests") stopMonitor();
  if (nextTab === "contests") await loadContests();
  if (nextTab === "new") await loadTemplates();
}

async function loadContests() {
  loadingContests.value = true;
  error.value = "";
  try {
    const response = await apiRequest("/api/v1/contests");
    contests.value = (response.contests || []).filter(
      (contest) => contest.created_by === props.user.id
    );
  } catch (loadError) {
    error.value = loadError.message || "Unable to load contests.";
  } finally {
    loadingContests.value = false;
  }
}

async function updateContestStatus(contest, status) {
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/contests/${contestId(contest)}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    replaceContest(updated);
    success.value = `Contest ${status.toLowerCase()} successfully.`;
  } catch (updateError) {
    error.value = updateError.message || "Contest update failed.";
  }
}

async function pauseContest(contest) {
  const id = contestId(contest);
  pausingContestId.value = id;
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/contests/${id}/pause`, {
      method: "PUT",
    });
    replaceContest(updated);
    success.value = `Contest "${contest.name}" paused.`;
  } catch (pauseError) {
    error.value = pauseError.message || "Pause failed.";
  } finally {
    pausingContestId.value = null;
  }
}

async function resumeContest(contest) {
  const id = contestId(contest);
  pausingContestId.value = id;
  error.value = "";
  success.value = "";
  try {
    const updated = await apiRequest(`/api/v1/contests/${id}/resume`, {
      method: "PUT",
    });
    replaceContest(updated);
    success.value = `Contest "${contest.name}" resumed.`;
  } catch (resumeError) {
    error.value = resumeError.message || "Resume failed.";
  } finally {
    pausingContestId.value = null;
  }
}

function askDeleteContest(contest) {
  deleteModal.contest = contest;
  deleteModal.open = true;
}

async function confirmDeleteContest() {
  const contest = deleteModal.contest;
  if (!contest) return;
  const id = contestId(contest);
  deleteModal.open = false;
  deletingContestId.value = id;
  error.value = "";
  success.value = "";
  try {
    await apiRequest(`/api/v1/contests/${id}`, { method: "DELETE" });
    contests.value = contests.value.filter((item) => contestId(item) !== id);
    success.value = `Contest "${contest.name}" deleted.`;
  } catch (deleteError) {
    error.value = deleteError.message || "Delete failed.";
  } finally {
    deletingContestId.value = null;
    deleteModal.contest = null;
  }
}

async function toggleContestDetails(contest) {
  const id = contestId(contest);
  if (expandedContestId.value === id) {
    expandedContestId.value = null;
    return;
  }
  expandedContestId.value = id;
  inviteEmails.value = "";
  await loadParticipants(contest);
  if (!leaderboards.value[id]) {
    loadingLeaderboardId.value = id;
    try {
      const response = await apiRequest(`/api/v1/contests/${id}/leaderboard`);
      leaderboards.value = { ...leaderboards.value, [id]: response.entries || [] };
    } catch (_) {
      leaderboards.value = { ...leaderboards.value, [id]: [] };
    } finally {
      loadingLeaderboardId.value = null;
    }
  }
}

async function loadParticipants(contest) {
  const id = contestId(contest);
  loadingParticipantsId.value = id;
  try {
    const [invitationsResponse, registrationsResponse] = await Promise.all([
      apiRequest(`/api/v1/contests/${id}/invitations`),
      apiRequest(`/api/v1/contest-registrations?contest_id=${id}`),
    ]);
    invitations.value = {
      ...invitations.value,
      [id]: invitationsResponse.invitations || [],
    };
    registrations.value = {
      ...registrations.value,
      [id]: registrationsResponse.registrations || [],
    };
  } catch (participantsError) {
    error.value = participantsError.message || "Unable to load participants.";
  } finally {
    loadingParticipantsId.value = null;
  }
}

async function sendInvitations(contest) {
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

async function removeParticipant(contest, registration) {
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

async function loadTemplates() {
  if (templates.value.length > 0) return;
  loadingTemplates.value = true;
  error.value = "";
  try {
    const response = await apiRequest("/api/v1/templates");
    templates.value = response.templates || [];
  } catch (loadError) {
    error.value = loadError.message || "Unable to load templates.";
  } finally {
    loadingTemplates.value = false;
  }
}

async function selectTemplate(template) {
  error.value = "";
  success.value = "";
  try {
    const fullTemplate = await apiRequest(`/api/v1/templates/${template.template_id}`);
    const now = new Date();
    const start = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    const end = new Date(now.getTime() + 8 * 24 * 60 * 60 * 1000);
    selectedTemplate.value = fullTemplate;
    Object.assign(form, {
      ...defaultForm(),
      name: fullTemplate.name,
      description: fullTemplate.description,
      visibility: "PUBLIC",
      start_date: toLocalDateTime(start.toISOString()),
      end_date: toLocalDateTime(end.toISOString()),
      sampling_rate_hz: fullTemplate.sampling_rate_hz,
      twin_id: fullTemplate.twin_id,
      initial_conditions: fullTemplate.initial_conditions || null,
      task_type: fullTemplate.task_type || "FORECASTING",
      metric_ids: fullTemplate.metric_ids || ["mae"],
      target_variables: fullTemplate.target_variables || [],
    });
    await loadCatalogProfile(fullTemplate.twin_id, fullTemplate);
    newStep.value = 2;
  } catch (templateError) {
    error.value = templateError.message || "Unable to load template.";
  }
}

async function loadCatalogProfile(twinId, template) {
  loadingCatalog.value = true;
  try {
    const profile = await apiRequest(`/api/v1/catalog/${twinId}`);
    catalogProfile.value = profile;
    const templateSensorMap = {};
    for (const config of template.sensor_configs || []) {
      templateSensorMap[config.sensor_id] = config;
    }
    const templateTargets = new Set(
      template.target_variables ||
        (template.sensor_configs || []).map((config) => config.sensor_id)
    );
    form.sensor_selections = profile.sensors.map((sensor) => {
      const config = templateSensorMap[sensor.sensor_id] || {};
      const enabled = sensor.sensor_id in templateSensorMap;
      return {
        sensor_id: sensor.sensor_id,
        name: sensor.name,
        unit: sensor.unit,
        enabled,
        target_selected: enabled && templateTargets.has(sensor.sensor_id),
        noise_std: config.noise_std ?? 0,
        gain: config.gain ?? 1,
        bias: config.bias ?? 0,
        drift_rate: config.drift_rate ?? 0,
        min_value: config.min_value ?? null,
        max_value: config.max_value ?? null,
        quantization: config.quantization ?? 0,
        latency_steps: config.latency_steps ?? 0,
        p_false_reading: config.p_false_reading ?? 0,
        p_outlier: config.p_outlier ?? 0,
      };
    });
    form.fault_entries = (template.fault_schedule || []).map((fault) => ({
      fault_id: fault.fault_id,
      start_time: fault.start_time ?? 0,
      end_time: fault.end_time ?? null,
      severity: fault.severity ?? 0.5,
    }));
  } finally {
    loadingCatalog.value = false;
  }
}

async function createContest() {
  const sensorConfigs = form.sensor_selections
    .filter((sensor) => sensor.enabled)
    .map((sensor) => {
      const config = { sensor_id: sensor.sensor_id };
      if (sensor.noise_std) config.noise_std = sensor.noise_std;
      if (sensor.gain !== 1) config.gain = sensor.gain;
      if (sensor.bias) config.bias = sensor.bias;
      if (sensor.drift_rate) config.drift_rate = sensor.drift_rate;
      return config;
    });
  const targetVariables = form.sensor_selections
    .filter((sensor) => sensor.enabled && sensor.target_selected)
    .map((sensor) => sensor.sensor_id);
  if (sensorConfigs.length === 0) {
    error.value = "Please enable at least one sensor.";
    return;
  }
  if (targetVariables.length === 0) {
    error.value = "Please select at least one forecast target.";
    return;
  }
  creating.value = true;
  error.value = "";
  success.value = "";
  try {
    const request = {
      name: form.name,
      description: form.description,
      visibility: form.visibility,
      task_type: form.task_type,
      metric_ids: form.metric_ids,
      twin_id: form.twin_id,
      sensor_configs: sensorConfigs,
      fault_schedule: form.fault_entries.map((fault) => ({
        fault_id: fault.fault_id,
        start_time: Number(fault.start_time),
        end_time: fault.end_time !== null && fault.end_time !== "" ? Number(fault.end_time) : null,
        severity: Number(fault.severity),
      })),
      initial_conditions: form.initial_conditions,
      sampling_rate_hz: Number(form.sampling_rate_hz),
      target_variables: targetVariables,
      start_date: toApiDateTime(form.start_date),
      end_date: toApiDateTime(form.end_date),
      end_of_observation: new Date(
        new Date(form.start_date).getTime() +
          Number(form.observation_horizon_days) * 86400 * 1000
      ).toISOString(),
      prediction_horizon_seconds: Number(form.prediction_horizon_seconds),
      score_against: form.score_against,
    };
    const created = await apiRequest("/api/v1/contests", {
      method: "POST",
      body: JSON.stringify(request),
    });
    contests.value = [created, ...contests.value];
    success.value = "Contest created successfully.";
    newStep.value = 1;
    selectedTemplate.value = null;
    tab.value = "contests";
  } catch (createError) {
    error.value = createError.message || "Contest creation failed.";
  } finally {
    creating.value = false;
  }
}

function appendMonitorObservation(observation) {
  if (observation.event) return;
  if (!monitorReady) {
    if (monitorBuffer.length < 300) monitorBuffer.push(observation);
    return;
  }
  const chart = monitorChart;
  if (!chart) return;
  const sensors = observation.sensors || {};
  const colors = ["#0d3b6e", "#0096c7", "#14b8a6", "#6366f1", "#f97316", "#64748b"];
  for (const sensorId of Object.keys(sensors)) {
    if (!chart.data.datasets.some((dataset) => dataset.label === sensorId)) {
      const color = colors[chart.data.datasets.length % colors.length];
      chart.data.datasets.push({
        label: sensorId,
        data: [],
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
      });
    }
  }
  chart.data.labels.push(observation.sequence_id);
  for (const dataset of chart.data.datasets) {
    dataset.data.push(sensors[dataset.label] ?? null);
    if (dataset.data.length > 150) dataset.data.shift();
  }
  if (chart.data.labels.length > 150) chart.data.labels.shift();
  if (!chart._rafPending) {
    chart._rafPending = true;
    requestAnimationFrame(() => {
      chart._rafPending = false;
      if (chart.canvas?.isConnected) chart.update("none");
    });
  }
}

function createMonitorChart() {
  const canvas = monitorChartCanvas.value;
  if (!canvas || typeof Chart === "undefined") return;
  if (canvas.offsetWidth === 0 || canvas.offsetHeight === 0) {
    setTimeout(createMonitorChart, 50);
    return;
  }
  Chart.getChart(canvas)?.destroy();
  canvas.width = canvas.parentElement.clientWidth || 600;
  canvas.height = canvas.parentElement.clientHeight || 288;
  monitorChart = new Chart(canvas, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      animation: false,
      responsive: false,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "nearest" },
      scales: {
        x: { ticks: { color: "#475569", maxTicksLimit: 10 }, grid: { color: "#e2e8f0" } },
        y: { ticks: { color: "#475569" }, grid: { color: "#e2e8f0" } },
      },
      plugins: { legend: { labels: { color: "#0f172a" } } },
    },
  });
  monitorReady = true;
  for (const observation of monitorBuffer) appendMonitorObservation(observation);
  monitorBuffer = [];
}

function openMonitorStream(contest) {
  const id = contestId(contest);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${window.location.host}/api/v1/ws/contests/${id}?token=${encodeURIComponent(props.token)}`;
  const connect = () => {
    if (!monitor.contest) return;
    const ws = new WebSocket(url);
    monitorSocket = ws;
    ws.onmessage = (event) => {
      const observation = JSON.parse(event.data);
      if (observation.event === "evaluation_started") {
        monitor.error = "Observation phase ended - the stream has closed.";
        return;
      }
      if (observation.event === "contest_closed") {
        monitor.error = "Contest has been closed.";
        return;
      }
      appendMonitorObservation(observation);
    };
    ws.onerror = () => {
      monitor.error = "Monitor stream connection failed.";
    };
    ws.onclose = () => {
      if (!monitor.contest) return;
      if (!monitor.error) {
        monitor.error = "Stream disconnected - reconnecting...";
        setTimeout(() => {
          if (monitor.contest) {
            monitor.error = "";
            connect();
          }
        }, 2000);
      }
    };
  };
  connect();
}

async function startMonitor(contest) {
  stopMonitor();
  monitor.contest = contest;
  monitor.error = "";
  monitorReady = false;
  monitorBuffer = [];
  openMonitorStream(contest);
  await nextTick();
  createMonitorChart();
}

function stopMonitor() {
  if (monitorSocket) {
    monitorSocket.close();
    monitorSocket = null;
  }
  if (monitorChart) {
    monitorChart.destroy();
    monitorChart = null;
  }
  monitor.contest = null;
  monitorReady = false;
  monitorBuffer = [];
}

function logout() {
  stopMonitor();
  auth.clearToken();
  emit("logout");
}

onMounted(() => {
  loadContests();
});

onBeforeUnmount(() => {
  stopMonitor();
});
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-slate-900">
    <nav class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div class="flex items-center gap-3">
          <img src="/assets/favicon.svg" alt="" class="h-9 w-9" />
          <div>
            <div class="text-lg font-semibold text-epic-deep">EPIC</div>
            <div class="text-xs font-medium uppercase tracking-wide text-epic-cyan">Organizer</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="max-w-[12rem] truncate text-sm font-medium text-slate-700">
            {{ user.username }}
          </span>
          <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="logout">
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
              <h1 class="text-3xl font-semibold text-epic-deep">Organizer Dashboard</h1>
              <p class="mt-2 text-slate-600">Create contests from templates and manage contest lifecycle.</p>
            </div>
            <div class="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
              <button type="button" :class="tab === 'contests' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('contests')">
                My Contests
              </button>
              <button type="button" :class="tab === 'new' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'" class="rounded px-4 py-2 text-sm font-semibold transition" @click="setTab('new')">
                New Contest
              </button>
            </div>
          </div>

          <p v-if="error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="success" class="rounded-md bg-cyan-50 px-4 py-3 text-sm text-epic-navy">{{ success }}</p>

          <div v-if="tab === 'contests'" class="space-y-5">
            <div class="flex items-center justify-between gap-4">
              <h2 class="text-xl font-semibold text-slate-900">My Contests</h2>
              <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="loadContests">
                Refresh
              </button>
            </div>
            <p v-if="loadingContests" class="text-sm text-slate-500">Loading contests...</p>
            <div v-if="!loadingContests && contests.length === 0" class="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500">
              No contests have been created yet.
            </div>
            <div class="grid gap-4 lg:grid-cols-2">
              <article
                v-for="contest in contests"
                :key="contestId(contest)"
                class="rounded-md border border-slate-200 bg-slate-50 p-5 transition hover:border-cyan-200"
                @click="toggleContestDetails(contest)"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-lg font-semibold text-epic-deep">{{ contest.name }}</h3>
                  <span :class="statusBadgeClass(contest.status)" class="rounded-full px-2.5 py-1 text-xs font-semibold">{{ contest.status }}</span>
                  <span v-if="contest.end_of_observation && contest.status === 'ACTIVE'" :class="contestPhaseClass(contest)" class="rounded-full px-2.5 py-1 text-xs font-semibold">
                    {{ contestPhaseLabel(contest) }}
                  </span>
                </div>

                <div class="mt-3 flex flex-wrap gap-2" @click.stop>
                  <button v-if="contest.status === 'DRAFT'" type="button" class="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700" @click="updateContestStatus(contest, 'ACTIVE')">
                    Activate
                  </button>
                  <button v-if="contest.status === 'ACTIVE'" type="button" :disabled="pausingContestId === contestId(contest)" class="rounded-md bg-amber-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-60" @click="pauseContest(contest)">
                    {{ pausingContestId === contestId(contest) ? "Pausing..." : "Pause" }}
                  </button>
                  <button v-if="contest.status === 'PAUSED'" type="button" :disabled="pausingContestId === contestId(contest)" class="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60" @click="resumeContest(contest)">
                    {{ pausingContestId === contestId(contest) ? "Resuming..." : "Resume" }}
                  </button>
                  <button v-if="contest.status === 'ACTIVE'" type="button" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="monitor.contest && contestId(monitor.contest) === contestId(contest) ? stopMonitor() : startMonitor(contest)">
                    {{ monitor.contest && contestId(monitor.contest) === contestId(contest) ? "Stop Monitor" : "Monitor" }}
                  </button>
                  <button v-if="contest.status === 'ACTIVE'" type="button" class="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700" @click="updateContestStatus(contest, 'CLOSED')">
                    Close
                  </button>
                  <button v-if="contest.status !== 'ACTIVE'" type="button" :disabled="deletingContestId === contestId(contest)" class="rounded-md border border-red-300 bg-white px-3 py-2 text-sm font-semibold text-red-600 transition hover:border-red-500 hover:bg-red-50 disabled:opacity-60" @click="askDeleteContest(contest)">
                    {{ deletingContestId === contestId(contest) ? "Deleting..." : "Delete" }}
                  </button>
                </div>

                <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-slate-600 sm:grid-cols-3">
                  <div><dt class="font-medium text-slate-500">Twin</dt><dd>{{ contest.twin_id }}</dd></div>
                  <div><dt class="font-medium text-slate-500">Participants</dt><dd>{{ contest.participant_count ?? "-" }}</dd></div>
                  <div><dt class="font-medium text-slate-500">Start</dt><dd>{{ formatDate(contest.start_date) }}</dd></div>
                  <div><dt class="font-medium text-slate-500">Observation horizon</dt><dd>{{ formatDate(contest.end_of_observation) }}</dd></div>
                  <div><dt class="font-medium text-slate-500">Prediction horizon</dt><dd>{{ contest.prediction_horizon_seconds }} s</dd></div>
                  <div><dt class="font-medium text-slate-500">End</dt><dd>{{ formatDate(contest.end_date) }}</dd></div>
                </dl>

                <div v-if="expandedContestId === contestId(contest)" class="mt-5 rounded-md border border-slate-200 bg-white p-4" @click.stop>
                  <div class="mb-3 flex items-center justify-between">
                    <h4 class="font-semibold text-slate-900">Leaderboard</h4>
                    <span v-if="loadingLeaderboardId === contestId(contest)" class="text-sm text-slate-500">Loading...</span>
                  </div>
                  <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-200 text-sm">
                      <thead><tr class="text-left text-slate-500"><th class="py-2 pr-4 font-semibold">Rank</th><th class="py-2 pr-4 font-semibold">Username</th><th class="py-2 pr-4 font-semibold">Score</th></tr></thead>
                      <tbody class="divide-y divide-slate-200">
                        <tr v-for="entry in leaderboards[contestId(contest)] || []" :key="entry.user_id">
                          <td class="py-3 pr-4">{{ entry.rank }}</td>
                          <td class="py-3 pr-4">{{ entry.username }}</td>
                          <td class="py-3 pr-4">{{ formatScore(entry.score) }}</td>
                        </tr>
                        <tr v-if="(leaderboards[contestId(contest)] || []).length === 0"><td colspan="3" class="py-4 text-slate-500">No leaderboard entries yet.</td></tr>
                      </tbody>
                    </table>
                  </div>

                  <div class="mt-6 border-t border-slate-200 pt-4">
                    <div class="mb-3 flex items-center justify-between">
                      <h4 class="font-semibold text-slate-900">Participants</h4>
                      <span v-if="loadingParticipantsId === contestId(contest)" class="text-sm text-slate-500">Loading...</span>
                    </div>
                    <form class="mb-4" @submit.prevent="sendInvitations(contest)">
                      <label class="block">
                        <span class="text-sm font-medium text-slate-700">Invite participants by email</span>
                        <textarea v-model="inviteEmails" rows="2" placeholder="anna@example.com, marco@example.com - separate with commas, spaces, or new lines" class="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"></textarea>
                      </label>
                      <button type="submit" :disabled="sendingInvites" class="mt-2 rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep disabled:opacity-60">
                        {{ sendingInvites ? "Sending..." : "Send invitations" }}
                      </button>
                    </form>

                    <h5 class="mb-2 text-sm font-semibold text-slate-700">Invited</h5>
                    <table class="mb-4 min-w-full divide-y divide-slate-200 text-sm">
                      <thead><tr class="text-left text-slate-500"><th class="py-2 pr-4 font-semibold">Email</th><th class="py-2 pr-4 font-semibold">Status</th></tr></thead>
                      <tbody class="divide-y divide-slate-200">
                        <tr v-for="invitation in invitations[contestId(contest)] || []" :key="invitation.id">
                          <td class="py-2 pr-4">{{ invitation.email }}</td>
                          <td class="py-2 pr-4"><span :class="invitation.used ? 'rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800' : 'rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800'">{{ invitation.used ? "Accepted" : "Pending" }}</span></td>
                        </tr>
                        <tr v-if="(invitations[contestId(contest)] || []).length === 0"><td colspan="2" class="py-3 text-slate-500">No invitations sent yet.</td></tr>
                      </tbody>
                    </table>

                    <h5 class="mb-2 text-sm font-semibold text-slate-700">Registered</h5>
                    <table class="min-w-full divide-y divide-slate-200 text-sm">
                      <thead><tr class="text-left text-slate-500"><th class="py-2 pr-4 font-semibold">Username</th><th class="py-2 pr-4 font-semibold">Email</th><th class="py-2 pr-4 font-semibold">Status</th><th class="py-2 pr-4 font-semibold"></th></tr></thead>
                      <tbody class="divide-y divide-slate-200">
                        <tr v-for="registration in registrations[contestId(contest)] || []" :key="registration.registration_id">
                          <td class="py-2 pr-4">{{ registration.username }}</td>
                          <td class="py-2 pr-4">{{ registration.email }}</td>
                          <td class="py-2 pr-4">{{ registration.status }}</td>
                          <td class="py-2 pr-4 text-right"><button v-if="registration.status === 'REGISTERED'" type="button" class="text-xs font-semibold text-red-600 hover:text-red-800" @click="removeParticipant(contest, registration)">Remove</button></td>
                        </tr>
                        <tr v-if="(registrations[contestId(contest)] || []).length === 0"><td colspan="4" class="py-3 text-slate-500">No registered participants yet.</td></tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </article>
            </div>

            <div v-if="monitor.contest" class="space-y-3">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-base font-semibold text-slate-900">{{ monitor.contest.name }}</h3>
                  <p class="text-sm text-slate-500">Live sensor readings - read-only view</p>
                </div>
                <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="stopMonitor">
                  Stop
                </button>
              </div>
              <p v-if="monitor.error" class="rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-800">{{ monitor.error }}</p>
              <div class="rounded-md border border-slate-200 bg-white p-4">
                <div class="h-72">
                  <canvas id="monitorChartOrganizer" ref="monitorChartCanvas" class="h-full w-full"></canvas>
                </div>
              </div>
            </div>
          </div>

          <div v-if="tab === 'new'" class="space-y-5">
            <div v-if="newStep === 1" class="space-y-4">
              <div class="flex items-center justify-between gap-4">
                <h2 class="text-xl font-semibold text-slate-900">Choose a Template</h2>
                <span v-if="loadingTemplates" class="text-sm text-slate-500">Loading...</span>
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <button
                  v-for="template in templates"
                  :key="template.template_id"
                  type="button"
                  class="rounded-md border border-slate-200 bg-slate-50 p-5 text-left transition hover:border-epic-cyan hover:bg-cyan-50"
                  @click="selectTemplate(template)"
                >
                  <h3 class="text-lg font-semibold text-epic-deep">{{ template.name }}</h3>
                  <p class="mt-2 text-sm font-medium text-epic-cyan">{{ template.twin_id }}</p>
                  <p class="mt-3 text-sm leading-6 text-slate-600">{{ template.description }}</p>
                  <p class="mt-3 text-xs font-medium text-slate-500">
                    Targets: {{ (template.target_variables || []).join(", ") || "all selected sensors" }}
                  </p>
                </button>
              </div>
            </div>

            <form v-if="newStep === 2" class="space-y-5" @submit.prevent="createContest">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h2 class="text-xl font-semibold text-slate-900">Create Contest</h2>
                  <p class="mt-1 text-sm text-slate-600">Based on {{ selectedTemplate?.name }}</p>
                </div>
                <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy" @click="newStep = 1">
                  Back
                </button>
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">Contest name</span>
                  <input v-model="form.name" type="text" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
                </label>
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">Visibility</span>
                  <select v-model="form.visibility" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100">
                    <option value="PUBLIC">PUBLIC</option>
                    <option value="PRIVATE">PRIVATE</option>
                  </select>
                </label>
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">Start date</span>
                  <input v-model="form.start_date" type="datetime-local" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
                </label>
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">End date</span>
                  <input v-model="form.end_date" type="datetime-local" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
                </label>
                <label class="block">
                  <span class="text-sm font-medium text-slate-700">Sampling rate (Hz)</span>
                  <input v-model.number="form.sampling_rate_hz" type="number" min="0.1" step="0.1" required class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
                </label>
                <label class="block md:col-span-2">
                  <span class="text-sm font-medium text-slate-700">Description</span>
                  <textarea v-model="form.description" rows="3" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"></textarea>
                </label>
              </div>
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-sm font-medium text-slate-700">Sensors</span>
                  <span class="text-xs text-slate-400">Select sensors and forecast targets.</span>
                </div>
                <p v-if="loadingCatalog" class="text-sm text-slate-400">Loading sensors...</p>
                <div
                  v-for="sensor in form.sensor_selections"
                  :key="sensor.sensor_id"
                  class="rounded-md border bg-white p-3 transition"
                  :class="sensor.enabled ? 'border-cyan-300' : 'border-slate-200'"
                >
                  <div class="flex items-center gap-3">
                    <input v-model="sensor.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-epic-cyan focus:ring-cyan-200" />
                    <span class="font-medium text-slate-800">{{ sensor.name }}</span>
                    <span class="text-xs text-slate-400">{{ sensor.unit }}</span>
                    <label v-if="sensor.enabled" class="ml-auto inline-flex items-center gap-2 text-xs font-medium text-epic-navy">
                      <input v-model="sensor.target_selected" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-epic-cyan focus:ring-cyan-200" />
                      Forecast target
                    </label>
                  </div>
                </div>
              </div>
              <button type="submit" :disabled="creating" class="rounded-md bg-epic-navy px-5 py-3 text-sm font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-100 disabled:opacity-60">
                {{ creating ? "Creating..." : "Create" }}
              </button>
            </form>
          </div>
        </div>
      </div>
    </section>

    <div v-if="deleteModal.open" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4">
      <div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 class="text-lg font-semibold text-slate-900">Delete contest</h2>
        <p class="mt-2 text-sm text-slate-600">
          Delete {{ deleteModal.contest?.name }}?
        </p>
        <div class="mt-6 flex justify-end gap-3">
          <button type="button" class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700" @click="deleteModal.open = false">
            Cancel
          </button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white" @click="confirmDeleteContest">
            Delete
          </button>
        </div>
      </div>
    </div>
  </main>
</template>
