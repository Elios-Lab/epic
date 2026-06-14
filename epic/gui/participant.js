window.EPICParticipant = {
  methods: {
    async loadParticipantDashboard() {
      if (this.participant.dashboardLoaded) {
        return;
      }
      this.participant.dashboardLoaded = true;
      await this.loadActiveContests();
    },

    async setParticipantTab(tab) {
      this.participant.tab = tab;
      this.participant.error = "";
      this.participant.success = "";
      this.stopMonitor();
      if (tab === "contests") {
        await this.loadActiveContests();
      }
      if (tab === "activity") {
        this.disconnectContest();
        await this.loadMyActivity();
      }
    },

    async loadRegistrations() {
      const response = await this.apiRequest("/api/v1/contest-registrations");
      this.participant.registrations = response.registrations || [];
      this.participant.registeredContestIds = new Set(
        this.participant.registrations
          .filter((registration) => registration.status === "REGISTERED")
          .map((registration) => registration.contest_id)
      );
    },

    async loadActiveContests() {
      this.participant.loadingContests = true;
      this.participant.error = "";
      this.participant.success = "";
      try {
        await this.loadRegistrations();
        const response = await this.apiRequest("/api/v1/contests?status=ACTIVE");
        this.participant.activeContests = response.contests || [];
      } catch (error) {
        this.participant.error = error.message || "Unable to load active contests.";
      } finally {
        this.participant.loadingContests = false;
      }
    },

    isRegistered(contest) {
      return this.participant.registeredContestIds.has(this.contestId(contest));
    },

    async registerContest(contest) {
      this.participant.error = "";
      this.participant.success = "";
      const contestId = this.contestId(contest);
      try {
        await this.apiRequest("/api/v1/contest-registrations", {
          method: "POST",
          body: JSON.stringify({ contest_id: contestId }),
        });
        this.participant.registeredContestIds = new Set([
          ...this.participant.registeredContestIds,
          contestId,
        ]);
        this.participant.success = "Registration confirmed.";
      } catch (error) {
        if (error.status === 409 && error.message.includes("Already registered")) {
          this.participant.registeredContestIds = new Set([
            ...this.participant.registeredContestIds,
            contestId,
          ]);
          this.participant.success = "Registration confirmed.";
          return;
        }
        this.participant.error = error.message || "Registration failed.";
      }
    },

    connectContest(contest) {
      this.disconnectContest();
      this.participant.error = "";
      this.participant.success = "";
      this.participant.connectedContest = contest;
      this.participant.latestObservation = { sequence_id: null, timestamp: "" };
      this.participant.submissionPayload = JSON.stringify(
        {
          forecast: {
            sensor_id: [],
          },
        },
        null,
        2
      );
      this.$nextTick(() => {
        this.createSensorChart();
        this.openStream(contest);
      });
    },

    disconnectContest() {
      this.stopMonitor();
      if (this.streamSocket) {
        this.streamSocket.close();
        this.streamSocket = null;
      }
      if (this.sensorChart) {
        this.sensorChart.destroy();
        this.sensorChart = null;
      }
      this.participant.connectedContest = null;
    },

    createSensorChart() {
      if (!this.$refs.sensorChart || typeof Chart === "undefined") {
        return;
      }
      this.sensorChart = new Chart(this.$refs.sensorChart, {
        type: "line",
        data: {
          labels: [],
          datasets: [],
        },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            intersect: false,
            mode: "nearest",
          },
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
          plugins: {
            legend: {
              labels: { color: "#0f172a" },
            },
          },
        },
      });
    },

    openStream(contest) {
      const contestId = this.contestId(contest);
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${protocol}://${window.location.host}/api/v1/ws/contests/${contestId}?token=${encodeURIComponent(this.token)}`;
      this.streamSocket = new WebSocket(url);
      this.streamSocket.onmessage = (event) => {
        const observation = JSON.parse(event.data);
        this.participant.latestObservation = {
          sequence_id: observation.sequence_id,
          timestamp: observation.timestamp,
        };
        this.appendObservation(observation);
      };
      this.streamSocket.onerror = () => {
        this.participant.error = "Live stream connection failed.";
      };
      this.streamSocket.onclose = () => {
        if (this.participant.connectedContest) {
          this.participant.error = "Live stream disconnected.";
        }
      };
    },

    appendObservation(observation) {
      if (!this.sensorChart) {
        return;
      }
      const label = observation.sequence_id;
      const sensors = observation.sensors || {};
      const colors = ["#0d3b6e", "#0096c7", "#14b8a6", "#6366f1", "#f97316", "#64748b"];
      for (const sensorId of Object.keys(sensors)) {
        if (!this.sensorChart.data.datasets.some((dataset) => dataset.label === sensorId)) {
          const color = colors[this.sensorChart.data.datasets.length % colors.length];
          this.sensorChart.data.datasets.push({
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
      this.sensorChart.data.labels.push(label);
      for (const dataset of this.sensorChart.data.datasets) {
        dataset.data.push(sensors[dataset.label] ?? null);
        if (dataset.data.length > 100) {
          dataset.data.shift();
        }
      }
      if (this.sensorChart.data.labels.length > 100) {
        this.sensorChart.data.labels.shift();
      }
      this.sensorChart.update("none");
    },

    async submitPrediction() {
      this.participant.submitting = true;
      this.participant.error = "";
      this.participant.success = "";
      try {
        const payload = JSON.parse(this.participant.submissionPayload);
        const contestId = this.contestId(this.participant.connectedContest);
        const response = await this.apiRequest(
          `/api/v1/contests/${contestId}/submissions`,
          {
            method: "POST",
            body: JSON.stringify({
              task_id: "forecasting",
              payload,
            }),
          }
        );
        this.participant.success = `Submission ${response.submission_id} received.`;
      } catch (error) {
        this.participant.error = error.message || "Submission failed.";
      } finally {
        this.participant.submitting = false;
      }
    },

    async loadMyActivity() {
      this.participant.loadingActivity = true;
      this.participant.error = "";
      this.participant.success = "";
      try {
        await this.loadRegistrations();
        const registeredContestIds = Array.from(this.participant.registeredContestIds);
        const contestsResponse = await this.apiRequest("/api/v1/contests");
        const contestsById = new Map(
          (contestsResponse.contests || []).map((contest) => [this.contestId(contest), contest])
        );
        const activity = [];
        for (const contestId of registeredContestIds) {
          let contest = contestsById.get(contestId);
          if (!contest) {
            contest = await this.apiRequest(`/api/v1/contests/${contestId}`);
          }
          const submissionsResponse = await this.apiRequest(
            `/api/v1/contests/${contestId}/submissions`
          );
          const submissions = [];
          for (const submission of submissionsResponse.submissions || []) {
            let score = null;
            if (submission.status === "EVALUATED") {
              const scoresResponse = await this.apiRequest(
                `/api/v1/submissions/${submission.submission_id}/scores`
              );
              const scores = scoresResponse.scores || [];
              if (scores.length > 0) {
                score = scores.reduce((total, item) => total + Number(item.value), 0) / scores.length;
              }
            }
            submissions.push({ ...submission, score });
          }
          activity.push({ contest, submissions });
        }
        this.participant.activity = activity;
      } catch (error) {
        this.participant.error = error.message || "Unable to load activity.";
      } finally {
        this.participant.loadingActivity = false;
      }
    },
  },
};
