/**
 * charts.js
 * Chart.js dashboard charts for Lumen.
 *
 * Chart.js binds an internal reference to each <canvas> element. Creating a
 * second Chart on the same canvas without first calling .destroy() on the
 * previous instance triggers:
 *
 *   "Canvas is already in use. Chart with ID '0' must be destroyed before
 *    the canvas with ID 'donutChart' can be reused."
 *
 * This module guarantees exactly one Chart per canvas by:
 *   1. Storing every instance in a module-level map keyed by canvas ID.
 *   2. Calling .destroy() on the existing instance before every create.
 *   3. Guarding DOMContentLoaded so initCharts only auto-runs once.
 */
(function () {
  'use strict';

  // ── Instance registry ─────────────────────────────────────────────
  // Single source of truth for every chart this module creates.
  var instances = {};

  // Prevent DOMContentLoaded from firing initCharts more than once.
  var initialized = false;

  // ── Chart.js global defaults (dark theme) ─────────────────────────
  if (typeof Chart !== 'undefined') {
    Chart.defaults.color = 'rgba(255, 255, 255, 0.6)';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';

    Chart.defaults.plugins.legend.labels.color = 'rgba(255, 255, 255, 0.8)';
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(19, 19, 26, 0.95)';
    Chart.defaults.plugins.tooltip.titleColor = '#ffffff';
    Chart.defaults.plugins.tooltip.bodyColor = 'rgba(255, 255, 255, 0.8)';
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.2)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;

    Chart.defaults.scale.grid.color = 'rgba(255, 255, 255, 0.1)';
    Chart.defaults.scale.ticks.color = 'rgba(255, 255, 255, 0.6)';
  }

  // ── Helpers ────────────────────────────────────────────────────────

  /**
   * Safely destroy any Chart instance on a canvas — whether tracked by
   * our registry OR only known to Chart.js internally.
   */
  function destroyIfExists(canvas) {
    if (!canvas) return;
    var id = canvas.id || canvas;

    // 1. Destroy from our own registry
    if (instances[id]) {
      instances[id].destroy();
      delete instances[id];
    }

    // 2. Fallback: ask Chart.js for any instance it still knows about
    var chartJsRef = Chart.getChart(canvas);
    if (chartJsRef) {
      chartJsRef.destroy();
    }
  }

  /** Destroy every chart this module has created. */
  function destroyAllCharts() {
    Object.keys(instances).forEach(function (id) {
      if (instances[id]) {
        instances[id].destroy();
        delete instances[id];
      }
    });
  }

  // ── Data fetching ──────────────────────────────────────────────────

  function fetchChartData() {
    if (window.__CHART_DATA__) {
      return Promise.resolve(window.__CHART_DATA__);
    }

    return fetch('/api/dashboard-data')
      .then(function (resp) {
        if (!resp.ok) return null;
        return resp.json();
      })
      .catch(function () {
        console.log('Chart data not available on this page');
        return null;
      });
  }

  // ── Chart creators ─────────────────────────────────────────────────

  function createDonut(canvas, labels, values) {
    if (!canvas) return null;
    destroyIfExists(canvas);

    var instance = new Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            '#2f8de1', '#dfe0e2', '#bfbfbf', '#13a2b3', '#29c07a'
          ],
          borderWidth: 0,
          hoverOffset: 6
        }]
      },
      options: {
        cutout: '60%',
        plugins: {
          legend: { display: false },
          tooltip: { mode: 'index' }
        }
      }
    });

    instances[canvas.id] = instance;
    return instance;
  }

  function createLine(canvas, labels, values) {
    if (!canvas) return null;
    destroyIfExists(canvas);

    var instance = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Spending',
          data: values,
          tension: 0.3,
          pointRadius: 4,
          borderWidth: 2,
          fill: false
        }]
      },
      options: {
        scales: {
          x: { display: true },
          y: { display: true, beginAtZero: false }
        },
        plugins: { legend: { display: false } }
      }
    });

    instances[canvas.id] = instance;
    return instance;
  }

  // ── Main initializer ───────────────────────────────────────────────

  function initCharts() {
    // Skip on analytics page (has its own chart handling)
    if (document.querySelector('.analytics-dashboard')) {
      return Promise.resolve();
    }

    return fetchChartData().then(function (d) {
      if (!d) {
        console.log('No chart data available');
        return;
      }

      var data = (typeof d === 'string') ? JSON.parse(d) : d;

      // Donut
      var donutCanvas = document.getElementById('donutChart');
      if (donutCanvas && data.donut_labels && data.donut_values) {
        createDonut(donutCanvas, data.donut_labels, data.donut_values);
      }

      // Mini donut
      var miniCanvas = document.getElementById('miniDonut');
      if (miniCanvas && data.mini_labels && data.mini_values) {
        createDonut(miniCanvas, data.mini_labels, data.mini_values);
      }

      // Line chart
      var lineCanvas = document.getElementById('lineChart');
      if (lineCanvas && data.line_labels && data.line_values) {
        createLine(lineCanvas, data.line_labels, data.line_values);
      }
    }).catch(function (err) {
      console.error('Failed to init charts', err);
    });
  }

  // ── Bootstrap ──────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    if (initialized) return;   // guard against duplicate listeners
    initialized = true;
    initCharts();
  });

  // Expose for manual refresh (e.g. Refresh Data button)
  window.initCharts = initCharts;
  window.destroyAllCharts = destroyAllCharts;

})();