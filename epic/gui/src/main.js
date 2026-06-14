import { createApp } from "vue";
import Chart from "chart.js/auto";
import AuthShell from "./vue/AuthShell.vue";
import "./styles.css";

window.Chart = Chart;

createApp(AuthShell).mount("#auth-app");
