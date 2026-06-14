window.EPICMonitor = {
  methods: {
    startMonitor(contest) {
      this.stopMonitor();
      this.monitor.monitoredContest = contest;
      this.monitor.monitorError = "";
      this.$el._monitorChartReady = false;
      // Open the stream immediately so no messages are missed while the
      // chart initialises. Messages are buffered and flushed once the
      // chart is ready.
      this.$el._monitorBuffer = [];
      this.openMonitorStream(contest);
      this.$nextTick(() => this.createMonitorChart());
    },
    stopMonitor() {
      if (this.monitor.monitorSocket) {
        this.monitor.monitorSocket.close();
        this.monitor.monitorSocket = null;
      }
      if (this.$el._monitorChart) {
        this.$el._monitorChart.destroy();
        this.$el._monitorChart = null;
      }
      this.monitor.monitorChart = null;
      this.monitor.monitoredContest = null;
      this.$el._monitorChartReady = false;
      this.$el._monitorBuffer = [];
    },
    createMonitorChart() {
      const ids = [
        "monitorChartParticipant",
        "monitorChartOrganizer",
        "monitorChartAdmin",
      ];
      const canvas = ids
        .map((id) => document.getElementById(id))
        .find((el) => el && el.offsetParent !== null);
      if (!canvas || typeof Chart === "undefined") {
        setTimeout(() => this.createMonitorChart(), 50);
        return;
      }
      // Wait until the canvas has real pixel dimensions; x-show may still
      // be applying display:none on the parent at this tick.
      if (canvas.offsetWidth === 0 || canvas.offsetHeight === 0) {
        setTimeout(() => this.createMonitorChart(), 50);
        return;
      }
      Chart.getChart(canvas)?.destroy();
      this.$el._monitorChart = null;
      // Use responsive:false and explicit pixels to avoid Chart.js resize
      // loops caused by CSS percentage heights.
      canvas.width = canvas.parentElement.clientWidth || 600;
      canvas.height = canvas.parentElement.clientHeight || 288;
      this.$el._monitorChart = new Chart(canvas, {
        type: "line",
        data: { labels: [], datasets: [] },
        options: {
          animation: false,
          responsive: false,
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
      this.$el._monitorChartReady = true;
      for (const obs of this.$el._monitorBuffer || []) {
        this.appendMonitorObservation(obs);
      }
      this.$el._monitorBuffer = [];
    },
    openMonitorStream(contest) {
      const contestId = this.contestId(contest);
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${protocol}://${window.location.host}/api/v1/ws/contests/${contestId}?token=${encodeURIComponent(this.token)}`;
      const connect = () => {
        if (!this.monitor.monitoredContest) return;
        const ws = new WebSocket(url);
        this.monitor.monitorSocket = ws;
        ws.onmessage = (event) => {
          const observation = JSON.parse(event.data);
          if (observation.event === "evaluation_started") {
            this.monitor.monitorError =
              "Observation phase ended — the stream has closed.";
            return;
          }
          if (observation.event === "contest_closed") {
            this.monitor.monitorError = "Contest has been closed.";
            return;
          }
          this.appendMonitorObservation(observation);
        };
        ws.onerror = () => {
          this.monitor.monitorError = "Monitor stream connection failed.";
        };
        ws.onclose = () => {
          if (!this.monitor.monitoredContest) return;
          if (!this.monitor.monitorError) {
            this.monitor.monitorError = "Stream disconnected — reconnecting…";
            setTimeout(() => {
              if (this.monitor.monitoredContest) {
                this.monitor.monitorError = "";
                connect();
              }
            }, 2000);
          }
        };
      };
      connect();
    },
    appendMonitorObservation(observation) {
      if (observation.event) return;
      if (!this.$el._monitorChartReady) {
        if (!this.$el._monitorBuffer) this.$el._monitorBuffer = [];
        if (this.$el._monitorBuffer.length < 300) {
          this.$el._monitorBuffer.push(observation);
        }
        return;
      }
      const chart = this.$el._monitorChart;
      if (!chart) return;
      const sensors = observation.sensors || {};
      const colors = [
        "#0d3b6e",
        "#0096c7",
        "#14b8a6",
        "#6366f1",
        "#f97316",
        "#64748b",
      ];
      for (const sensorId of Object.keys(sensors)) {
        if (!chart.data.datasets.some((d) => d.label === sensorId)) {
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
      // Store the pending flag on the Chart object, not Alpine state, so
      // requestAnimationFrame never triggers a reactive re-render.
      if (!chart._rafPending) {
        chart._rafPending = true;
        requestAnimationFrame(() => {
          chart._rafPending = false;
          if (chart.canvas?.isConnected) chart.update("none");
        });
      }
    },
  },
};
