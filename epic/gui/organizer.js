window.EPICOrganizer = {
  methods: {
    async loadOrganizerDashboard() {
      if (this.organizer.dashboardLoaded) {
        return;
      }
      this.organizer.dashboardLoaded = true;
      await this.loadOrganizerContests();
    },
    async setOrganizerTab(tab) {
      this.organizer.tab = tab;
      this.organizer.error = "";
      this.organizer.success = "";
      if (tab !== "contests") this.stopMonitor();
      if (tab === "contests") {
        await this.loadOrganizerContests();
      }
      if (tab === "new") {
        await this.loadTemplates();
      }
    },
    async loadOrganizerContests() {
      this.organizer.loadingContests = true;
      this.organizer.error = "";
      try {
        const response = await this.apiRequest("/api/v1/contests");
        const all = response.contests || [];
        // "My Contests": the listing also includes public contests by
        // other organizers; keep only the ones this user created.
        this.organizer.contests = all.filter(
          (contest) => contest.created_by === this.user.id
        );
      } catch (error) {
        this.organizer.error = error.message || "Unable to load contests.";
      } finally {
        this.organizer.loadingContests = false;
      }
    },
    async updateContestStatus(contest, status) {
      this.organizer.error = "";
      this.organizer.success = "";
      try {
        const contestId = this.contestId(contest);
        const updated = await this.apiRequest(`/api/v1/contests/${contestId}`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        });
        this.replaceOrganizerContest(updated);
        this.organizer.success = `Contest ${status.toLowerCase()} successfully.`;
      } catch (error) {
        this.organizer.error = error.message || "Contest update failed.";
      }
    },
    startDeadlineExtension(contest) {
      this.organizer.extendingContestId = this.contestId(contest);
      this.organizer.newEndDate = this.toLocalDateTime(contest.end_date);
      this.organizer.error = "";
      this.organizer.success = "";
    },
    async extendContestDeadline(contest) {
      this.organizer.error = "";
      this.organizer.success = "";
      try {
        const contestId = this.contestId(contest);
        const updated = await this.apiRequest(`/api/v1/contests/${contestId}`, {
          method: "PATCH",
          body: JSON.stringify({
            end_date: this.toApiDateTime(this.organizer.newEndDate),
          }),
        });
        this.replaceOrganizerContest(updated);
        this.organizer.extendingContestId = null;
        this.organizer.newEndDate = "";
        this.organizer.success = "Deadline updated successfully.";
      } catch (error) {
        this.organizer.error = error.message || "Deadline update failed.";
      }
    },
    replaceOrganizerContest(updated) {
      const updatedId = this.contestId(updated);
      this.organizer.contests = this.organizer.contests.map((contest) =>
        this.contestId(contest) === updatedId ? updated : contest
      );
    },
    async toggleLeaderboard(contest) {
      const contestId = this.contestId(contest);
      if (this.organizer.expandedContestId === contestId) {
        this.organizer.expandedContestId = null;
        return;
      }
      this.organizer.expandedContestId = contestId;
      this.organizer.inviteEmails = "";
      await this.loadParticipants(contest);
      if (this.organizer.leaderboards[contestId]) {
        return;
      }
      this.organizer.loadingLeaderboardId = contestId;
      this.organizer.error = "";
      try {
        const response = await this.apiRequest(
          `/api/v1/contests/${contestId}/leaderboard`
        );
        this.organizer.leaderboards = {
          ...this.organizer.leaderboards,
          [contestId]: response.entries || [],
        };
      } catch (error) {
        this.organizer.error = error.message || "Unable to load leaderboard.";
        this.organizer.leaderboards = {
          ...this.organizer.leaderboards,
          [contestId]: [],
        };
      } finally {
        this.organizer.loadingLeaderboardId = null;
      }
    },
    async loadTemplates() {
      if (this.organizer.templates.length > 0) {
        return;
      }
      this.organizer.loadingTemplates = true;
      this.organizer.error = "";
      try {
        const response = await this.apiRequest("/api/v1/templates");
        this.organizer.templates = response.templates || [];
      } catch (error) {
        this.organizer.error = error.message || "Unable to load templates.";
      } finally {
        this.organizer.loadingTemplates = false;
      }
    },
    async selectTemplate(template) {
      this.organizer.error = "";
      this.organizer.success = "";
      try {
        const fullTemplate = await this.apiRequest(
          `/api/v1/templates/${template.template_id}`
        );
        const now = new Date();
        const start = new Date(now.getTime() + 24 * 60 * 60 * 1000);
        const end = new Date(now.getTime() + 8 * 24 * 60 * 60 * 1000);
        this.organizer.selectedTemplate = fullTemplate;
        this.organizer.form = {
          name: fullTemplate.name,
          description: fullTemplate.description,
          visibility: "PUBLIC",
          start_date: this.toLocalDateTime(start.toISOString()),
          end_date: this.toLocalDateTime(end.toISOString()),
          sampling_rate_hz: fullTemplate.sampling_rate_hz,
          twin_id: fullTemplate.twin_id,
          sensor_selections: [],
          fault_entries: [],
          initial_conditions: fullTemplate.initial_conditions || null,
          task_type: fullTemplate.task_type || "FORECASTING",
          metric_ids: fullTemplate.metric_ids || ["mae"],
          score_against: "ground_truth",
          target_variables: fullTemplate.target_variables || [],
          observation_horizon_days: 2,
          prediction_horizon_seconds: 3600,
        };
        await this.loadCatalogProfile(fullTemplate.twin_id, fullTemplate);
        this.organizer.newStep = 2;
      } catch (error) {
        this.organizer.error = error.message || "Unable to load template.";
      }
    },
    async loadCatalogProfile(twin_id, template) {
      this.organizer.loadingCatalog = true;
      try {
        const profile = await this.apiRequest(`/api/v1/catalog/${twin_id}`);
        this.organizer.catalogProfile = profile;
        const templateSensorMap = {};
        for (const sc of template.sensor_configs || []) {
          templateSensorMap[sc.sensor_id] = sc;
        }
        const templateTargets = new Set(
          template.target_variables ||
            (template.sensor_configs || []).map((sc) => sc.sensor_id)
        );
        this.organizer.form.sensor_selections = profile.sensors.map((sensor) => {
          const tc = templateSensorMap[sensor.sensor_id] || {};
          const enabled = sensor.sensor_id in templateSensorMap;
          return {
            sensor_id: sensor.sensor_id,
            name: sensor.name,
            unit: sensor.unit,
            enabled: enabled,
            target_selected: enabled && templateTargets.has(sensor.sensor_id),
            noise_std: tc.noise_std ?? 0.0,
            gain: tc.gain ?? 1.0,
            bias: tc.bias ?? 0.0,
            drift_rate: tc.drift_rate ?? 0.0,
            min_value: tc.min_value ?? null,
            max_value: tc.max_value ?? null,
            quantization: tc.quantization ?? 0.0,
            latency_steps: tc.latency_steps ?? 0,
            p_false_reading: tc.p_false_reading ?? 0.0,
            p_outlier: tc.p_outlier ?? 0.0,
            showAdvanced: false,
          };
        });
        this.organizer.form.fault_entries = (template.fault_schedule || []).map(
          (fe) => ({
            fault_id: fe.fault_id,
            start_time: fe.start_time ?? 0,
            end_time: fe.end_time ?? null,
            severity: fe.severity ?? 0.5,
          })
        );
      } finally {
        this.organizer.loadingCatalog = false;
      }
    },
    addFaultEntry() {
      const faults = this.organizer.catalogProfile?.faults || [];
      if (faults.length === 0) return;
      this.organizer.form.fault_entries.push({
        fault_id: faults[0].fault_id,
        start_time: 0,
        end_time: null,
        severity: 0.5,
      });
    },
    removeFaultEntry(idx) {
      this.organizer.form.fault_entries.splice(idx, 1);
    },
    async createContest() {
      const sensor_configs = this.organizer.form.sensor_selections
        .filter((s) => s.enabled)
        .map((s) => {
          const cfg = { sensor_id: s.sensor_id };
          if (s.noise_std) cfg.noise_std = s.noise_std;
          if (s.gain !== 1.0) cfg.gain = s.gain;
          if (s.bias) cfg.bias = s.bias;
          if (s.drift_rate) cfg.drift_rate = s.drift_rate;
          if (s.min_value !== null && s.min_value !== "") {
            cfg.min_value = Number(s.min_value);
          }
          if (s.max_value !== null && s.max_value !== "") {
            cfg.max_value = Number(s.max_value);
          }
          if (s.quantization) cfg.quantization = s.quantization;
          if (s.latency_steps) cfg.latency_steps = s.latency_steps;
          if (s.p_false_reading) cfg.p_false_reading = s.p_false_reading;
          if (s.p_outlier) cfg.p_outlier = s.p_outlier;
          return cfg;
        });
      if (sensor_configs.length === 0) {
        this.organizer.error = "Please enable at least one sensor.";
        return;
      }
      const target_variables = this.organizer.form.sensor_selections
        .filter((s) => s.enabled && s.target_selected)
        .map((s) => s.sensor_id);
      if (target_variables.length === 0) {
        this.organizer.error = "Please select at least one forecast target.";
        return;
      }
      const fault_schedule = this.organizer.form.fault_entries.map((fe) => ({
        fault_id: fe.fault_id,
        start_time: Number(fe.start_time),
        end_time:
          fe.end_time !== null && fe.end_time !== ""
            ? Number(fe.end_time)
            : null,
        severity: Number(fe.severity),
      }));
      this.organizer.creating = true;
      this.organizer.error = "";
      this.organizer.success = "";
      try {
        const request = {
          name: this.organizer.form.name,
          description: this.organizer.form.description,
          visibility: this.organizer.form.visibility,
          task_type: this.organizer.form.task_type,
          metric_ids: this.organizer.form.metric_ids,
          twin_id: this.organizer.form.twin_id,
          sensor_configs: sensor_configs,
          fault_schedule: fault_schedule,
          initial_conditions: this.organizer.form.initial_conditions,
          sampling_rate_hz: Number(this.organizer.form.sampling_rate_hz),
          target_variables: target_variables,
          start_date: this.toApiDateTime(this.organizer.form.start_date),
          end_date: this.toApiDateTime(this.organizer.form.end_date),
          end_of_observation: new Date(
            new Date(this.organizer.form.start_date).getTime() +
              Number(this.organizer.form.observation_horizon_days) *
                86400 *
                1000
          ).toISOString(),
          prediction_horizon_seconds: Number(
            this.organizer.form.prediction_horizon_seconds
          ),
          score_against: this.organizer.form.score_against,
        };
        const created = await this.apiRequest("/api/v1/contests", {
          method: "POST",
          body: JSON.stringify(request),
        });
        this.organizer.contests = [created, ...this.organizer.contests];
        this.organizer.success = "Contest created successfully.";
        this.organizer.newStep = 1;
        this.organizer.selectedTemplate = null;
        this.organizer.tab = "contests";
      } catch (error) {
        this.organizer.error = error.message || "Contest creation failed.";
      } finally {
        this.organizer.creating = false;
      }
    },
  },
};
