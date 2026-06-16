<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { auth } from "../auth.js";
import AdminDashboard from "./AdminDashboard.vue";
import OrganizerDashboard from "./OrganizerDashboard.vue";
import ParticipantDashboard from "./ParticipantDashboard.vue";

const routeIsRegistration = () => window.location.pathname === "/register";
const token = ref(auth.getToken());
const tokenPayload = ref(token.value ? auth.decodeToken(token.value) : null);
const authenticated = ref(Boolean(token.value));
const view = ref(routeIsRegistration() ? "register" : "landing");
const loading = ref(false);
const error = ref("");
const originalToken = ref(null);
const impersonating = ref("");

const credentials = reactive({
  username: "",
  password: "",
});

const organizerRequest = reactive({
  submitting: false,
  error: "",
  success: "",
  form: {
    first_name: "",
    last_name: "",
    email: "",
    phone_number: "",
    password: "",
    password_confirm: "",
  },
});

const registration = reactive({
  token: "",
  checking: false,
  valid: false,
  submitting: false,
  contestName: "",
  email: "",
  error: "",
  form: {
    first_name: "",
    last_name: "",
    phone_number: "",
    password: "",
    password_confirm: "",
  },
});

const isParticipant = computed(
  () => authenticated.value && tokenPayload.value?.role === "PARTICIPANT"
);
const isOrganizer = computed(
  () => authenticated.value && tokenPayload.value?.role === "ORGANIZER"
);
const isAdmin = computed(
  () => authenticated.value && tokenPayload.value?.role === "ADMINISTRATOR"
);
const currentUser = computed(() => ({
  id: tokenPayload.value?.sub || "",
  username: tokenPayload.value?.username || "",
  role: tokenPayload.value?.role || "",
}));
const shouldRenderPublic = computed(
  () =>
    (!authenticated.value || routeIsRegistration()) &&
    !isParticipant.value &&
    !isOrganizer.value &&
    !isAdmin.value
);

function syncAuthState() {
  token.value = auth.getToken();
  tokenPayload.value = token.value ? auth.decodeToken(token.value) : null;
  authenticated.value = Boolean(token.value);
}

function showLogin() {
  error.value = "";
  view.value = "login";
}

function showOrganizerRequest() {
  error.value = "";
  organizerRequest.error = "";
  organizerRequest.success = "";
  view.value = "organizerRequest";
}

function returnHome() {
  window.location.assign("/");
}

function handleParticipantLogout() {
  token.value = null;
  tokenPayload.value = null;
  authenticated.value = false;
  originalToken.value = null;
  impersonating.value = "";
  view.value = "landing";
}

function handleOrganizerLogout() {
  handleParticipantLogout();
}

function handleAdminLogout() {
  handleParticipantLogout();
}

function handleImpersonate(event) {
  originalToken.value = token.value;
  impersonating.value = event.username;
  token.value = event.token;
  tokenPayload.value = auth.decodeToken(event.token);
  authenticated.value = true;
  auth.storeToken(event.token);
}

function stopImpersonating() {
  if (!originalToken.value) return;
  auth.storeToken(originalToken.value);
  token.value = originalToken.value;
  tokenPayload.value = auth.decodeToken(originalToken.value);
  authenticated.value = true;
  originalToken.value = null;
  impersonating.value = "";
}

async function login() {
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    });
    if (!response.ok) {
      throw new Error("Invalid username or password.");
    }
    const data = await response.json();
    auth.storeToken(data.access_token);
    credentials.password = "";
    window.location.replace("/");
  } catch (loginError) {
    error.value = loginError.message || "Login failed.";
    auth.clearToken();
  } finally {
    loading.value = false;
  }
}

async function submitOrganizerRequest() {
  organizerRequest.error = "";
  organizerRequest.success = "";
  if (organizerRequest.form.password !== organizerRequest.form.password_confirm) {
    organizerRequest.error = "Passwords do not match.";
    return;
  }
  organizerRequest.submitting = true;
  try {
    const response = await fetch("/api/v1/organizer-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: organizerRequest.form.first_name,
        last_name: organizerRequest.form.last_name,
        email: organizerRequest.form.email,
        phone_number: organizerRequest.form.phone_number || null,
        password: organizerRequest.form.password,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error?.message || "Organizer access request failed.");
    }
    organizerRequest.success =
      "Request submitted. An administrator will review it and notify you by email.";
    Object.assign(organizerRequest.form, {
      first_name: "",
      last_name: "",
      email: "",
      phone_number: "",
      password: "",
      password_confirm: "",
    });
  } catch (requestError) {
    organizerRequest.error =
      requestError.message || "Organizer access request failed.";
  } finally {
    organizerRequest.submitting = false;
  }
}

async function startRegistration(inviteToken) {
  view.value = "register";
  registration.token = inviteToken;
  registration.error = "";
  if (!inviteToken) {
    registration.valid = false;
    registration.error = "This invitation link is missing its token.";
    return;
  }
  registration.checking = true;
  try {
    const response = await fetch(
      `/api/v1/invitations/${encodeURIComponent(inviteToken)}`
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.valid) {
      registration.valid = false;
      registration.error =
        "This invitation link is invalid, expired, or already used.";
      return;
    }
    registration.valid = true;
    registration.contestName = data.contest_name || "an EPIC contest";
    registration.email = data.email || "";
  } catch (registrationError) {
    registration.valid = false;
    registration.error = "Could not verify the invitation. Please try again.";
  } finally {
    registration.checking = false;
  }
}

async function acceptInvitation() {
  registration.error = "";
  if (registration.form.password !== registration.form.password_confirm) {
    registration.error = "Passwords do not match.";
    return;
  }
  registration.submitting = true;
  try {
    const response = await fetch(
      `/api/v1/invitations/${encodeURIComponent(registration.token)}/accept`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: registration.form.first_name,
          last_name: registration.form.last_name,
          phone_number: registration.form.phone_number || null,
          password: registration.form.password,
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
    auth.storeToken(data.access_token);
    registration.form.password = "";
    registration.form.password_confirm = "";
    window.location.replace("/");
  } catch (acceptError) {
    registration.error = acceptError.message || "Registration failed.";
  } finally {
    registration.submitting = false;
  }
}

onMounted(() => {
  window.addEventListener("epic-auth-changed", syncAuthState);
  if (routeIsRegistration()) {
    const inviteToken = new URLSearchParams(window.location.search).get("token");
    startRegistration(inviteToken || "");
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("epic-auth-changed", syncAuthState);
});
</script>

<template>
  <div
    v-if="impersonating"
    class="flex items-center justify-between gap-4 bg-amber-400 px-6 py-2 text-sm font-semibold text-amber-900"
  >
    <span>Impersonating {{ impersonating }}</span>
    <button
      type="button"
      class="rounded-md bg-amber-900 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-amber-800"
      @click="stopImpersonating"
    >
      Stop
    </button>
  </div>
  <ParticipantDashboard
    v-if="isParticipant && !routeIsRegistration()"
    :token="token"
    :user="currentUser"
    @logout="handleParticipantLogout"
  />
  <OrganizerDashboard
    v-else-if="isOrganizer && !routeIsRegistration()"
    :token="token"
    :user="currentUser"
    @logout="handleOrganizerLogout"
  />
  <AdminDashboard
    v-else-if="isAdmin && !routeIsRegistration()"
    :token="token"
    :user="currentUser"
    @logout="handleAdminLogout"
    @impersonate="handleImpersonate"
  />
  <main
    v-else-if="shouldRenderPublic"
    class="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(0,150,199,0.28),transparent_32rem),linear-gradient(135deg,#061a33_0%,#0d3b6e_52%,#04101f_100%)] text-white"
  >
    <section
      v-if="view === 'landing'"
      class="mx-auto grid min-h-screen w-full max-w-6xl gap-10 px-6 py-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center"
    >
      <div class="space-y-8">
        <div class="inline-flex rounded-md bg-white p-4 shadow-2xl shadow-cyan-950/30">
          <img
            src="/assets/epic_logo.svg"
            alt="EPIC logo"
            class="w-72 max-w-[72vw] sm:w-96"
          />
        </div>
        <div class="max-w-2xl space-y-5">
          <h1 class="text-5xl font-semibold tracking-normal text-white sm:text-6xl">
            EPIC
          </h1>
          <p class="text-xl leading-8 text-cyan-50">
            A simulation-driven machine learning competition platform based on digital twins.
          </p>
        </div>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="inline-flex items-center rounded-md bg-cyan-400 px-6 py-3 text-base font-semibold text-epic-deep shadow-lg shadow-cyan-950/30 transition hover:bg-cyan-300 focus:outline-none focus:ring-4 focus:ring-cyan-200/50"
            @click="showLogin"
          >
            Log in
          </button>
          <button
            type="button"
            class="inline-flex items-center rounded-md border border-cyan-200/70 px-6 py-3 text-base font-semibold text-cyan-50 transition hover:border-cyan-100 hover:bg-white/10 focus:outline-none focus:ring-4 focus:ring-cyan-200/30"
            @click="showOrganizerRequest"
          >
            Request organizer access
          </button>
        </div>
      </div>
      <div class="rounded-lg border border-cyan-300/20 bg-white/8 p-6 shadow-2xl shadow-cyan-950/20 backdrop-blur">
        <div class="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
          <div class="rounded-md border border-white/10 bg-white/10 p-5">
            <div class="text-sm font-medium uppercase tracking-wide text-cyan-200">
              Sensor Streams
            </div>
            <div class="mt-2 text-base leading-6 text-white/90">
              Observe live sensor data from running simulations and build your predictions in real time.
            </div>
          </div>
          <div class="rounded-md border border-white/10 bg-white/10 p-5">
            <div class="text-sm font-medium uppercase tracking-wide text-cyan-200">
              Open Competitions
            </div>
            <div class="mt-2 text-base leading-6 text-white/90">
              Organizers publish contests with configurable tasks, schedules, and fault injection scenarios.
            </div>
          </div>
          <div class="rounded-md border border-white/10 bg-white/10 p-5">
            <div class="text-sm font-medium uppercase tracking-wide text-cyan-200">
              Automatic Scoring
            </div>
            <div class="mt-2 text-base leading-6 text-white/90">
              Submit your full forecast and let the platform score it automatically against the hidden ground truth.
            </div>
          </div>
        </div>
      </div>
    </section>

    <section
      v-else-if="view === 'login'"
      class="flex min-h-screen items-center justify-center px-6 py-12"
    >
      <div class="w-full max-w-md rounded-lg border border-cyan-300/20 bg-white p-8 text-slate-900 shadow-2xl shadow-cyan-950/30">
        <button
          type="button"
          class="mb-6 text-sm font-medium text-epic-navy hover:text-epic-cyan"
          @click="view = 'landing'; error = ''"
        >
          Back
        </button>
        <img src="/assets/epic_logo.svg" alt="EPIC logo" class="mb-8 w-48" />
        <h2 class="text-2xl font-semibold text-epic-deep">Log in to EPIC</h2>
        <form class="mt-6 space-y-5" @submit.prevent="login">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Username</span>
            <input
              v-model="credentials.username"
              type="text"
              autocomplete="username"
              required
              class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"
            />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Password</span>
            <input
              v-model="credentials.password"
              type="password"
              autocomplete="current-password"
              required
              class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100"
            />
          </label>
          <p v-if="error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ error }}
          </p>
          <button
            type="submit"
            :disabled="loading"
            class="w-full rounded-md bg-epic-navy px-5 py-3 font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ loading ? "Logging in..." : "Log in" }}
          </button>
        </form>
      </div>
    </section>

    <section
      v-else-if="view === 'organizerRequest'"
      class="flex min-h-screen items-center justify-center px-6 py-12"
    >
      <div class="w-full max-w-2xl rounded-lg border border-cyan-300/20 bg-white p-8 text-slate-900 shadow-2xl shadow-cyan-950/30">
        <button
          type="button"
          class="mb-6 text-sm font-medium text-epic-navy hover:text-epic-cyan"
          @click="view = 'landing'; organizerRequest.error = ''; organizerRequest.success = ''"
        >
          Back
        </button>
        <h2 class="text-2xl font-semibold text-epic-deep">Request organizer access</h2>
        <p class="mt-3 text-sm leading-6 text-slate-600">
          Tell us who you are and choose the password you will use if your request is approved.
        </p>

        <div
          v-if="organizerRequest.success"
          class="mt-6 rounded-md bg-cyan-50 px-4 py-4 text-sm text-epic-navy"
        >
          <p>{{ organizerRequest.success }}</p>
          <button
            type="button"
            class="mt-4 rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep"
            @click="showLogin"
          >
            Go to login
          </button>
        </div>

        <form
          v-else
          class="mt-6 space-y-4"
          @submit.prevent="submitOrganizerRequest"
        >
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block">
              <span class="text-sm font-medium text-slate-700">First name</span>
              <input v-model="organizerRequest.form.first_name" type="text" required autocomplete="given-name" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Last name</span>
              <input v-model="organizerRequest.form.last_name" type="text" required autocomplete="family-name" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
          </div>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Email</span>
            <input v-model="organizerRequest.form.email" type="email" required autocomplete="email" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Phone number (optional)</span>
            <input v-model="organizerRequest.form.phone_number" type="tel" autocomplete="tel" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
          </label>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Password</span>
              <input v-model="organizerRequest.form.password" type="password" required minlength="8" autocomplete="new-password" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Confirm password</span>
              <input v-model="organizerRequest.form.password_confirm" type="password" required minlength="8" autocomplete="new-password" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
          </div>
          <p
            v-if="organizerRequest.error"
            class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {{ organizerRequest.error }}
          </p>
          <button
            type="submit"
            :disabled="organizerRequest.submitting"
            class="w-full rounded-md bg-epic-navy px-5 py-3 font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ organizerRequest.submitting ? "Submitting..." : "Submit request" }}
          </button>
        </form>
      </div>
    </section>

    <section
      v-else-if="view === 'register'"
      class="flex min-h-screen items-center justify-center px-6 py-12"
    >
      <div class="w-full max-w-md rounded-lg border border-cyan-300/20 bg-white p-8 text-slate-900 shadow-2xl shadow-cyan-950/30">
        <h2 class="text-2xl font-semibold text-epic-deep">Join EPIC</h2>
        <p v-if="registration.checking" class="mt-4 text-sm text-slate-600">
          Checking your invitation...
        </p>
        <div v-else-if="!registration.valid" class="mt-6 space-y-4">
          <p class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ registration.error || "This invitation link is invalid, expired, or already used." }}
          </p>
          <button
            type="button"
            class="rounded-md bg-epic-navy px-4 py-2 text-sm font-semibold text-white transition hover:bg-epic-deep"
            @click="returnHome"
          >
            Return to EPIC
          </button>
        </div>
        <div v-else>
          <p class="mt-3 text-sm leading-6 text-slate-600">
            You were invited to <span class="font-semibold text-epic-navy">{{ registration.contestName }}</span>.
            Complete registration for <span class="font-medium">{{ registration.email }}</span>.
          </p>
          <form class="mt-6 space-y-4" @submit.prevent="acceptInvitation">
            <div class="grid gap-4 sm:grid-cols-2">
              <label class="block">
                <span class="text-sm font-medium text-slate-700">First name</span>
                <input v-model="registration.form.first_name" type="text" required autocomplete="given-name" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
              </label>
              <label class="block">
                <span class="text-sm font-medium text-slate-700">Last name</span>
                <input v-model="registration.form.last_name" type="text" required autocomplete="family-name" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
              </label>
            </div>
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Phone number (optional)</span>
              <input v-model="registration.form.phone_number" type="tel" autocomplete="tel" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Password</span>
              <input v-model="registration.form.password" type="password" required minlength="8" autocomplete="new-password" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
            <label class="block">
              <span class="text-sm font-medium text-slate-700">Confirm password</span>
              <input v-model="registration.form.password_confirm" type="password" required minlength="8" autocomplete="new-password" class="mt-2 w-full rounded-md border border-slate-300 px-4 py-3 text-slate-900 outline-none transition focus:border-epic-cyan focus:ring-4 focus:ring-cyan-100" />
            </label>
            <p v-if="registration.error" class="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              {{ registration.error }}
            </p>
            <button
              type="submit"
              :disabled="registration.submitting"
              class="w-full rounded-md bg-epic-navy px-5 py-3 font-semibold text-white transition hover:bg-epic-deep focus:outline-none focus:ring-4 focus:ring-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {{ registration.submitting ? "Creating account..." : "Create account" }}
            </button>
          </form>
        </div>
      </div>
    </section>
  </main>
</template>
