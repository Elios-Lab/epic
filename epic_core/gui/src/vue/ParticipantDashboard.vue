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
const loadingActivity = ref(false);
const submitting = ref(false);
const activeContests = ref([]);
const registrations = ref([]);
const registeredContestIds = ref(new Set());
const connectedContest = ref(null);
const sensorChartCanvas = ref(null);
const sensorChart = ref(null);
const streamSocket = ref(null);
const activity = ref([]);
const latestObservation = reactive({ sequence_id: null, timestamp: "" });
const submissionPayload = ref(
  JSON.stringify({ forecast: { sensor_id: [] } }, null, 2)
);

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

function contestPhaseLabel(contest) {
  return formatters.contestPhaseLabel(contest);
}

function contestPhaseClass(contest) {
  return formatters.contestPhaseClass(contest);
}

async function setParticipantTab(nextTab) {
  tab.value = nextTab;
  error.value = "";
  success.value = "";
  stopStream();
  if (nextTab === "contests") {
    await loadActiveContests();
  }
  if (nextTab === "activity") {
    disconnectContest();
    await loadMyActivity();
  }
}

async function loadRegistrations() {
  const response = await apiRequest("/api/v1/contest-registrations");
  registrations.value = response.registrations || [];
  registeredContestIds.value = new Set(
    registrations.value
      .filter((registration) => registration.status === "REGISTERED")
      .map((registration) => registration.contest_id)
  );
}

async function loadActiveContests() {
  loadingContests.value = true;
  error.value = "";
  success.value = "";
  try {
    await loadRegistrations();
    const response = await apiRequest("/api/v1/contests?status=ACTIVE");
    activeContests.value = response.contests || [];
  } catch (loadError) {
    error.value = loadError.message || "Unable to load active contests.";
  } finally {
    loadingContests.value = false;
  }
}

function isRegistered(contest) {
  return registeredContestIds.value.has(contestId(contest));
}

async function registerContest(contest) {
  error.value = "";
  success.value = "";
  const id = contestId(contest);
  try {
    await apiRequest("/api/v1/contest-registrations", {
      method: "POST",
      body: JSON.stringify({ contest_id: id }),
    });
    registeredContestIds.value = new Set([...registeredContestIds.value, id]);
    success.value = "Registration confirmed.";
  } catch (registrationError) {
    if (
      registrationError.status === 409 &&
      registrationError.message.includes("Already registered")
    ) {
      registeredContestIds.value = new Set([...registeredContestIds.value, id]);
      success.value = "Registration confirmed.";
      return;
    }
    error.value = registrationError.message || "Registration failed.";
  }
}

function createSensorChart() {
  const canvas = sensorChartCanvas.value;
  if (!canvas || typeof Chart === "undefined") {
    return;
  }
  sensorChart.value = new Chart(canvas, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "nearest" },
      scales: {
        x: {
          ticks: { color: "#475569", maxTicksLimit: 10 },
          grid: { color: "#e2e8f0" },
        },
        y: {
          ticks: { color: "#475569" },
          grid: { color: "#e2e8f0" },
        },
      },
      plugins: { legend: { labels: { color: "#0f172a" } } },
    },
  });
}

function appendObservation(observation) {
  if (!sensorChart.value) return;
  const sensors = observation.sensors || {};
  const colors = ["#0d3b6e", "#0096c7", "#14b8a6", "#6366f1", "#f97316", "#64748b"];
  for (const sensorId of Object.keys(sensors)) {
    if (!sensorChart.value.data.datasets.some((dataset) => dataset.label === sensorId)) {
      const color = colors[sensorChart.value.data.datasets.length % colors.length];
      sensorChart.value.data.datasets.push({
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
  sensorChart.value.data.labels.push(observation.sequence_id);
  for (const dataset of sensorChart.value.data.datasets) {
    dataset.data.push(sensors[dataset.label] ?? null);
    if (dataset.data.length > 100) dataset.data.shift();
  }
  if (sensorChart.value.data.labels.length > 100) {
    sensorChart.value.data.labels.shift();
  }
  sensorChart.value.update("none");
}

function openStream(contest) {
  const id = contestId(contest);
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${window.location.host}/api/v1/ws/contests/${id}?token=${encodeURIComponent(props.token)}`;
  streamSocket.value = new WebSocket(url);
  streamSocket.value.onmessage = (event) => {
    const observation = JSON.parse(event.data);
    latestObservation.sequence_id = observation.sequence_id;
    latestObservation.timestamp = observation.timestamp;
    appendObservation(observation);
  };
  streamSocket.value.onerror = () => {
    error.value = "Live stream connection failed.";
  };
  streamSocket.value.onclose = () => {
    if (connectedContest.value) {
      error.value = "Live stream disconnected.";
    }
  };
}

function stopStream() {
  if (streamSocket.value) {
    streamSocket.value.close();
    streamSocket.value = null;
  }
  if (sensorChart.value) {
    sensorChart.value.destroy();
    sensorChart.value = null;
  }
}

async function connectContest(contest) {
  disconnectContest();
  error.value = "";
  success.value = "";
  connectedContest.value = contest;
  latestObservation.sequence_id = null;
  latestObservation.timestamp = "";
  submissionPayload.value = JSON.stringify({ forecast: { sensor_id: [] } }, null, 2);
  await nextTick();
  createSensorChart();
  openStream(contest);
}

function disconnectContest() {
  stopStream();
  connectedContest.value = null;
}

async function submitPrediction() {
  submitting.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload = JSON.parse(submissionPayload.value);
    const id = contestId(connectedContest.value);
    const response = await apiRequest(`/api/v1/contests/${id}/submissions`, {
      method: "POST",
      body: JSON.stringify({ task_id: "forecasting", payload }),
    });
    success.value = `Submission ${response.submission_id} received.`;
  } catch (submitError) {
    error.value = submitError.message || "Submission failed.";
  } finally {
    submitting.value = false;
  }
}

async function loadMyActivity() {
  loadingActivity.value = true;
  error.value = "";
  success.value = "";
  try {
    await loadRegistrations();
    const contestsResponse = await apiRequest("/api/v1/contests");
    const contestsById = new Map(
      (contestsResponse.contests || []).map((contest) => [contestId(contest), contest])
    );
    const nextActivity = [];
    for (const id of Array.from(registeredContestIds.value)) {
      let contest = contestsById.get(id);
      if (!contest) {
        contest = await apiRequest(`/api/v1/contests/${id}`);
      }
      const submissionsResponse = await apiRequest(`/api/v1/contests/${id}/submissions`);
      const submissions = [];
      for (const submission of submissionsResponse.submissions || []) {
        let score = null;
        if (submission.status === "EVALUATED") {
          const scoresResponse = await apiRequest(
            `/api/v1/submissions/${submission.submission_id}/scores`
          );
          const scores = scoresResponse.scores || [];
          if (scores.length > 0) {
            score =
              scores.reduce((total, item) => total + Number(item.value), 0) /
              scores.length;
          }
        }
        submissions.push({ ...submission, score });
      }
      nextActivity.push({ contest, submissions });
    }
    activity.value = nextActivity;
  } catch (activityError) {
    error.value = activityError.message || "Unable to load activity.";
  } finally {
    loadingActivity.value = false;
  }
}

function logout() {
  disconnectContest();
  auth.clearToken();
  emit("logout");
}

onMounted(() => {
  loadActiveContests();
});

onBeforeUnmount(() => {
  disconnectContest();
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
            <div class="text-xs font-medium uppercase tracking-wide text-epic-cyan">
              Participant
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="max-w-[12rem] truncate text-sm font-medium text-slate-700">
            {{ user.username }}
          </span>
          <button
            type="button"
            class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy"
            @click="logout"
          >
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
              <h1 class="text-3xl font-semibold text-epic-deep">
                Participant Dashboard
              </h1>
              <p class="mt-2 text-slate-600">
                Join active contests, watch live sensor streams, and submit predictions.
              </p>
            </div>
            <div class="inline-flex rounded-md border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                :class="tab === 'contests' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'"
                class="rounded px-4 py-2 text-sm font-semibold transition"
                @click="setParticipantTab('contests')"
              >
                Contests
              </button>
              <button
                type="button"
                :class="tab === 'activity' ? 'bg-white text-epic-navy shadow-sm' : 'text-slate-600 hover:text-epic-navy'"
                class="rounded px-4 py-2 text-sm font-semibold transition"
                @click="setParticipantTab('activity')"
              >
                My Activity
              </button>
            </div>
          </div>

          <p v-if="error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ error }}
          </p>
          <p v-if="success" class="rounded-md bg-cyan-50 px-4 py-3 text-sm text-epic-navy">
            {{ success }}
          </p>

          <div v-if="tab === 'contests'" class="space-y-6">
            <details class="rounded-md border border-cyan-200 bg-cyan-50">
              <summary class="cursor-pointer px-5 py-3 text-sm font-semibold text-epic-navy select-none">
                Getting started - quickstart notebook
              </summary>
              <div class="space-y-3 px-5 pb-5 pt-2 text-sm leading-6 text-slate-700">
                <p>
                  Use the quickstart notebook to follow the participant workflow:
                  register for a contest, collect live sensor data, build a baseline
                  forecast, submit it, and inspect the score.
                </p>
                <a
                  href="/notebooks/quickstart.ipynb"
                  class="inline-flex rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-100"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open quickstart notebook
                </a>
              </div>
            </details>

            <div v-if="!connectedContest" class="space-y-5">
              <div class="flex items-center justify-between gap-4">
                <h2 class="text-xl font-semibold text-slate-900">Active Contests</h2>
                <button
                  type="button"
                  class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy"
                  @click="loadActiveContests"
                >
                  Refresh
                </button>
              </div>
              <p v-if="loadingContests" class="text-sm text-slate-500">
                Loading active contests...
              </p>
              <div
                v-if="!loadingContests && activeContests.length === 0"
                class="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500"
              >
                No active contests are available right now.
              </div>
              <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <article
                  v-for="contest in activeContests"
                  :key="contestId(contest)"
                  class="rounded-md border border-slate-200 bg-slate-50 p-5"
                >
                  <div class="flex min-h-28 flex-col justify-between gap-4">
                    <div>
                      <h3 class="text-lg font-semibold text-epic-deep">
                        {{ contest.name }}
                      </h3>
                      <dl class="mt-3 space-y-2 text-sm text-slate-600">
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">Twin</dt>
                          <dd class="text-right">{{ contest.twin_id }}</dd>
                        </div>
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">Sampling</dt>
                          <dd>{{ contest.sampling_rate_hz }} Hz</dd>
                        </div>
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">Start</dt>
                          <dd class="text-right">{{ formatDate(contest.start_date) }}</dd>
                        </div>
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">Observation horizon</dt>
                          <dd class="text-right">{{ formatDate(contest.end_of_observation) }}</dd>
                        </div>
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">Prediction horizon</dt>
                          <dd class="text-right">{{ contest.prediction_horizon_seconds }} s</dd>
                        </div>
                        <div class="flex justify-between gap-4">
                          <dt class="font-medium text-slate-500">End</dt>
                          <dd class="text-right">{{ formatDate(contest.end_date) }}</dd>
                        </div>
                      </dl>
                    </div>
                    <div class="flex flex-wrap gap-2">
                      <button
                        type="button"
                        class="rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-100"
                        @click="isRegistered(contest) ? connectContest(contest) : registerContest(contest)"
                      >
                        {{ isRegistered(contest) ? "Connect" : "Register" }}
                      </button>
                    </div>
                  </div>
                </article>
              </div>
            </div>

            <div v-else class="space-y-6">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 class="text-xl font-semibold text-slate-900">
                    {{ connectedContest.name }}
                  </h2>
                  <p class="mt-1 text-sm text-slate-500">
                    Live stream from {{ connectedContest.twin_id }}
                  </p>
                </div>
                <button
                  type="button"
                  class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy"
                  @click="disconnectContest"
                >
                  Disconnect
                </button>
              </div>
              <div class="rounded-md border border-slate-200 bg-white p-4">
                <div class="h-80">
                  <canvas ref="sensorChartCanvas" class="h-full w-full"></canvas>
                </div>
              </div>
              <div class="grid gap-4 sm:grid-cols-3">
                <div class="rounded-md bg-slate-50 p-4">
                  <div class="text-sm font-medium text-slate-500">Latest sequence</div>
                  <div class="mt-1 text-2xl font-semibold text-epic-deep">
                    {{ latestObservation.sequence_id ?? "-" }}
                  </div>
                </div>
                <div class="rounded-md bg-slate-50 p-4">
                  <div class="text-sm font-medium text-slate-500">Latest timestamp</div>
                  <div class="mt-1 text-lg font-semibold text-epic-deep">
                    {{ latestObservation.timestamp || "-" }}
                  </div>
                </div>
                <div class="rounded-md p-4" :class="contestPhaseClass(connectedContest)">
                  <div class="text-sm font-medium opacity-70">Phase</div>
                  <div class="mt-1 text-lg font-semibold">
                    {{ contestPhaseLabel(connectedContest) || "Observation" }}
                  </div>
                </div>
              </div>
              <form class="rounded-md border border-slate-200 bg-slate-50 p-5" @submit.prevent="submitPrediction">
                <h3 class="text-lg font-semibold text-slate-900">Submit Prediction</h3>
                <p class="mt-1 text-sm text-slate-500">
                  Provide one list of predicted values per required target variable.
                </p>
                <label class="mt-4 block">
                  <span class="text-sm font-medium text-slate-700">Forecast payload JSON</span>
                  <textarea
                    v-model="submissionPayload"
                    rows="8"
                    class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 font-mono text-sm text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"
                  ></textarea>
                </label>
                <button
                  type="submit"
                  :disabled="submitting"
                  class="mt-5 rounded-md bg-epic-navy px-5 py-3 text-sm font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {{ submitting ? "Submitting..." : "Submit" }}
                </button>
              </form>
            </div>
          </div>

          <div v-if="tab === 'activity'" class="space-y-5">
            <div class="flex items-center justify-between gap-4">
              <h2 class="text-xl font-semibold text-slate-900">My Activity</h2>
              <button
                type="button"
                class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-epic-cyan hover:text-epic-navy"
                @click="loadMyActivity"
              >
                Refresh
              </button>
            </div>
            <p v-if="loadingActivity" class="text-sm text-slate-500">Loading activity...</p>
            <div
              v-if="!loadingActivity && activity.length === 0"
              class="rounded-md border border-dashed border-slate-300 p-8 text-center text-slate-500"
            >
              No registered contest activity yet.
            </div>
            <section
              v-for="contestActivity in activity"
              :key="contestId(contestActivity.contest)"
              class="rounded-md border border-slate-200 bg-slate-50 p-5"
            >
              <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <h3 class="text-lg font-semibold text-epic-deep">
                  {{ contestActivity.contest.name }}
                </h3>
                <span class="text-sm font-semibold text-epic-cyan">
                  {{ contestActivity.contest.status }}
                </span>
              </div>
              <div class="mt-4 overflow-x-auto">
                <table class="min-w-full divide-y divide-slate-200 text-sm">
                  <thead>
                    <tr class="text-left text-slate-500">
                      <th class="py-2 pr-4 font-semibold">Submitted</th>
                      <th class="py-2 pr-4 font-semibold">Status</th>
                      <th class="py-2 pr-4 font-semibold">Score</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-200 bg-white">
                    <tr
                      v-for="submission in contestActivity.submissions"
                      :key="submission.submission_id"
                    >
                      <td class="py-3 pr-4">{{ formatDate(submission.submitted_at) }}</td>
                      <td class="py-3 pr-4">{{ submission.status }}</td>
                      <td class="py-3 pr-4">{{ formatScore(submission.score) }}</td>
                    </tr>
                    <tr v-if="contestActivity.submissions.length === 0">
                      <td colspan="3" class="py-4 text-slate-500">No submissions yet.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
